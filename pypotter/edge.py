"""Keep MQTT wake control separate from the process that serves requests."""

import logging
import os
import signal
import subprocess
import sys
from multiprocessing import Pipe
from multiprocessing.connection import Connection
from threading import Condition, Thread
from typing import Protocol

from pypotter.config import Settings, get_settings

logger = logging.getLogger(__name__)
MODES = {b"ON": "on", b"HEADLESS": "headless", b"OFF": "off"}


class ShutdownPipe(Protocol):
    def recv_bytes(self, maxlength: int, /) -> bytes: ...
    def close(self) -> None: ...


def serve(
    settings: Settings, host: str, port: int, mode: str, shutdown_pipe: ShutdownPipe | None = None
) -> int:
    import uvicorn

    from pypotter.api.app import create_app

    app = create_app(settings, ui_enabled=mode == "on")
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=settings.log_level.lower(),
            access_log=settings.access_log,
            limit_concurrency=settings.max_connections,
            timeout_keep_alive=2,
            timeout_graceful_shutdown=12,
        )
    )
    if shutdown_pipe is not None:

        def watch_parent(pipe: ShutdownPipe):
            try:
                pipe.recv_bytes(1)
            except (EOFError, OSError):
                pass
            finally:
                pipe.close()
                server.should_exit = True

        Thread(target=watch_parent, args=(shutdown_pipe,), daemon=True, name="parent-pipe").start()
    server.run()
    return 0 if server.started else 1


class EdgeController:
    def __init__(self, settings: Settings, host: str, port: int):
        import paho.mqtt.client as mqtt

        from pypotter.integrations.mqtt import configure_client

        if not settings.mqtt_host:
            raise ValueError("Set PYPOTTER_MQTT_HOST to enable MQTT control.")
        self.mqtt_host = settings.mqtt_host
        self.mqtt_port = settings.mqtt_port
        prefix = settings.mqtt_topic_prefix.strip("/")
        self.command_topic = f"{prefix}/edge/set"
        self.state_topic = f"{prefix}/edge/state"
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"{settings.mqtt_client_id}-edge"
        )
        configure_client(
            self.client,
            self.mqtt_host,
            settings.mqtt_username,
            settings.mqtt_password,
            settings.mqtt_tls,
        )
        self.client.will_set(self.state_topic, "UNAVAILABLE", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.condition = Condition()
        self.target: str | None = settings.edge_mode
        self.refresh_state = False
        self.stopping = False
        self.worker: subprocess.Popen | None = None
        self.watcher: Thread | None = None
        self.shutdown_pipe: ShutdownPipe | None = None
        self.mode = "off"
        self.host = host
        self.port = port

    def _on_connect(self, client, userdata, flags, reason, properties):
        if reason != 0:
            logger.warning("MQTT edge connection refused: %s", reason)
            return
        client.subscribe(self.command_topic, qos=1)
        with self.condition:
            self.refresh_state = True
            self.condition.notify()

    def _on_message(self, client, userdata, message):
        if message.topic != self.command_topic or len(message.payload) > 16:
            return
        target = MODES.get(message.payload.strip().upper())
        if target:
            with self.condition:
                self.target = target
                self.condition.notify()

    def _watch_worker(self, worker):
        worker.wait()
        with self.condition:
            self.condition.notify()

    def _start_worker(self, mode: str):
        read_end, write_end = Pipe(duplex=False)
        handle = read_end.fileno()
        command = [
            sys.executable,
            "-m",
            "pypotter.edge",
            self.host,
            str(self.port),
            mode,
            str(handle),
        ]
        try:
            if sys.platform == "win32":
                # Inherit just the private pipe, keeping stdin available for native libraries.
                os.set_handle_inheritable(handle, True)
                startup = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [handle]})
                env = None
                if sys.prefix != sys.base_prefix:
                    # Bypass the Windows venv redirector, which can drop inherited handles.
                    command[0] = getattr(sys, "_base_executable", sys.executable)
                    env = {**os.environ, "__PYVENV_LAUNCHER__": sys.executable}
                worker = subprocess.Popen(command, env=env, startupinfo=startup, close_fds=True)
            else:
                worker = subprocess.Popen(command, pass_fds=(handle,))
        except OSError:
            write_end.close()
            raise
        finally:
            read_end.close()
        self.worker = worker
        self.shutdown_pipe = write_end
        self.watcher = Thread(
            target=self._watch_worker, args=(worker,), daemon=True, name="web-worker-exit"
        )
        self.watcher.start()

    def _stop_worker(self):
        worker, self.worker = self.worker, None
        if worker is None:
            return
        assert self.shutdown_pipe is not None and self.watcher is not None
        self.shutdown_pipe.close()
        self.shutdown_pipe = None
        try:
            worker.wait(timeout=15)
        except subprocess.TimeoutExpired:
            logger.warning("Web worker did not stop in 15 seconds; terminating it")
            worker.kill()
            worker.wait()
        self.watcher.join()
        self.watcher = None

    def _shutdown(self, *_):
        with self.condition:
            self.stopping = True
            self.condition.notify()

    def _work_pending(self) -> bool:
        return (
            self.stopping
            or self.refresh_state
            or self.target is not None
            or (self.worker is not None and self.worker.poll() is not None)
        )

    def run(self) -> int:
        previous_signals = {
            sig: signal.signal(sig, self._shutdown) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            self.client.connect_async(self.mqtt_host, self.mqtt_port, keepalive=60)
            self.client.loop_start()
            while True:
                with self.condition:
                    self.condition.wait_for(self._work_pending)
                    if self.stopping:
                        break
                    target, self.target = self.target, None
                    publish_state = self.refresh_state
                    self.refresh_state = False
                if self.worker is not None and self.worker.poll() is not None:
                    logger.error("Web worker exited with status %s", self.worker.returncode)
                    self._stop_worker()
                    self.mode = "error"
                    publish_state = True
                if target is not None and target != self.mode:
                    self._stop_worker()
                    self.mode = target
                    publish_state = True
                    if target != "off":
                        try:
                            self._start_worker(target)
                        except OSError:
                            logger.exception("Cannot launch web worker")
                            self.mode = "error"
                if publish_state and self.client.is_connected():
                    self.client.publish(self.state_topic, self.mode.upper(), qos=1, retain=True)
        finally:
            self._stop_worker()
            try:
                if self.client.is_connected():
                    published = self.client.publish(
                        self.state_topic, "UNAVAILABLE", qos=1, retain=True
                    )
                    if published.rc == 0:
                        published.wait_for_publish(timeout=1)
            except RuntimeError as exc:
                logger.warning("Could not publish edge shutdown state: %s", exc)
            finally:
                self.client.disconnect()
                self.client.loop_stop()
                for sig, handler in previous_signals.items():
                    signal.signal(sig, handler)
        return 0


def run_web(host: str, port: int) -> int:
    settings = get_settings()
    if not settings.enable_mqtt:
        if settings.edge_mode == "off":
            raise ValueError("Edge mode OFF requires MQTT so the service can be woken.")
        return serve(settings, host, port, settings.edge_mode)
    logging.basicConfig(level=settings.log_level.upper())
    return EdgeController(settings, host, port).run()


if __name__ == "__main__":
    host, port, mode, handle = sys.argv[1:]
    shutdown_pipe: ShutdownPipe
    if sys.platform == "win32":
        from multiprocessing.connection import PipeConnection

        shutdown_pipe = PipeConnection(int(handle), writable=False)
    else:
        shutdown_pipe = Connection(int(handle), writable=False)
    raise SystemExit(serve(get_settings(), host, int(port), mode, shutdown_pipe))
