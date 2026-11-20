# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import argparse
import base64
import logging
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from math import dist
from pathlib import Path
from urllib.parse import urlsplit

import requests

from HassApi import HassApi
from pypotter.config import get_settings
from pypotter.services.processor import SAMPLE_SIZE, ProcessingError, SpellProcessor, opencv

logger = logging.getLogger("pypotter.camera")
FLOW_SETTINGS = {
    "winSize": (25, 25),
    "maxLevel": 7,
}


class WandTracker:
    def __init__(self):
        self.previous_frame = None
        self.points = None
        self.path = []
        self.recent_distances = deque(maxlen=10)
        self.distance = 0.0

    def reset(self):
        self.previous_frame = None
        self.points = None
        self.path.clear()
        self.recent_distances.clear()
        self.distance = 0.0

    def update(self, cv2, frame):
        if self.points is None:
            self.points = cv2.goodFeaturesToTrack(frame, 5, 0.01, 30)
            self.previous_frame = frame if self.points is not None else None
            return None

        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            self.previous_frame, frame, self.points, None, **FLOW_SETTINGS
        )
        if next_points is None or status is None:
            self.reset()
            return None
        tracked = next_points[status.ravel() == 1]
        if not len(tracked):
            self.reset()
            return None

        self.points = tracked.reshape(-1, 1, 2)
        self.previous_frame = frame
        for x, y in tracked:
            point = float(x), float(y)
            if self.path:
                distance = dist(self.path[-1], point)
                self.recent_distances.append(distance)
                self.distance += distance
            self.path.append(point)

        if len(self.path) >= 256:
            self.reset()
        elif len(self.path) > 15 and sum(self.recent_distances) / len(self.recent_distances) < 0.5:
            path = self.path[:] if self.distance > 100 else None
            self.reset()
            return path
        return None


def render_path(cv2, path, frame_shape):
    import numpy as np

    points = np.asarray(path, dtype=np.int32)
    x, y, width, height = cv2.boundingRect(points)
    left, top = max(x - 35, 0), max(y - 15, 0)
    right = min(x + width + 35, frame_shape[1])
    bottom = min(y + height + 15, frame_shape[0])
    image = np.zeros((bottom - top, right - left), dtype=np.uint8)
    cv2.polylines(image, [points - np.array([left, top], dtype=np.int32)], False, 255, 10)
    return image



def submit_gesture(url, token, encoded):
    try:
        response = requests.post(
            f"{url}/api/v1/camera/recognitions",
            headers={"Authorization": f"Bearer {token}"},
            json={"image_base64": base64.b64encode(encoded).decode("ascii")},
            timeout=(3, 15),
            allow_redirects=False,
        )
        if response.status_code not in {201, 204}:
            logger.warning("PyPotter declined the camera gesture (HTTP %s)", response.status_code)
    except requests.RequestException:
        logger.warning("PyPotter could not confirm receipt of the camera gesture")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recognize wand gestures from an IR camera")
    parser.add_argument("source")
    parser.add_argument("home_assistant_url", nargs="?")
    parser.add_argument("api_token", nargs="?")
    parser.add_argument("--pypotter-url", help="Send completed gestures to the PyPotter API")
    parser.add_argument("--preview", action="store_true", help="Show camera windows in API mode")
    parser.add_argument("--no-background", action="store_true", help="Skip background subtraction")
    parser.add_argument("remove_background", nargs="?", default="True")
    parser.add_argument("show_windows", nargs="?", default="True")
    parser.add_argument("training", nargs="?", default="False")
    parser.add_argument("debug_fps", nargs="?", default="False")
    args = parser.parse_args(argv)
    if args.pypotter_url:
        if args.home_assistant_url or args.api_token:
            parser.error("--pypotter-url uses PYPOTTER_API_TOKEN instead of legacy arguments")
        token = get_settings().api_token
        url = args.pypotter_url.rstrip("/")
        try:
            parts = urlsplit(url)
            valid = (
                parts.hostname
                and parts.username is None
                and parts.password is None
                and not parts.query
                and not parts.fragment
                and (
                    parts.scheme == "https"
                    or (
                        parts.scheme == "http"
                        and parts.hostname in {"localhost", "127.0.0.1", "::1"}
                    )
                )
            )
        except ValueError:
            valid = False
        if not valid or not token:
            parser.error("Provide an HTTPS PyPotter URL (HTTP on loopback) and PYPOTTER_API_TOKEN")
    elif not args.home_assistant_url or not args.api_token:
        parser.error("Provide --pypotter-url or both legacy Home Assistant arguments")

    cv2 = opencv()
    logging.basicConfig(level=logging.INFO if args.debug_fps == "True" else logging.WARNING)
    source = int(args.source) if args.source.isdecimal() else args.source
    training_dir = Path(os.environ.get("PYPOTTER_TRAINING_DIR", Path(__file__).parent / "Training"))
    processor = SpellProcessor(training_dir) if not args.pypotter_url else None
    tracker = WandTracker()
    hass = HassApi(args.home_assistant_url, args.api_token) if processor else None
    uploader = ThreadPoolExecutor(max_workers=1) if args.pypotter_url else None
    upload = None
    show_windows = args.preview if uploader else args.show_windows == "True"
    remove_background = args.remove_background == "True" and not args.no_background
    background = cv2.createBackgroundSubtractorMOG2() if remove_background else None
    capture = None
    frame_count = 0
    report_at = time.monotonic() + 1
    retry_delay = 1
    try:
        while True:
            if capture is None:
                capture = cv2.VideoCapture(source)
            ok, frame = capture.read()
            if not ok:
                capture.release()
                capture = None
                tracker.reset()
                if show_windows and cv2.waitKey(1) == 27:
                    break
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 8)
                continue

            retry_delay = 1
            cv2.flip(frame, 1, frame)
            if show_windows:
                cv2.imshow("Original", frame)
            if background is not None:
                mask = background.apply(frame, learningRate=0.001)
                frame = cv2.bitwise_and(frame, frame, mask=mask)
                del mask
                if show_windows:
                    cv2.imshow("BackgroundRemoved", frame)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            del frame
            _, threshold = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            del gray
            path = tracker.update(cv2, threshold)
            if show_windows:
                cv2.imshow("Threshold", threshold)
            if path:
                gesture = render_path(cv2, path, threshold.shape)
                if uploader:
                    if upload and not upload.done():
                        logger.warning("Camera gesture skipped while another cast is in progress")
                    else:
                        sample = cv2.resize(gesture, (SAMPLE_SIZE, SAMPLE_SIZE))
                        ok, encoded = cv2.imencode(".png", sample)
                        if ok:
                            upload = uploader.submit(submit_gesture, url, token, encoded.tobytes())
                else:
                    try:
                        result = processor.classify(gesture, include_mistakes=True)
                        if args.training == "True":
                            filename = f"char{time.time_ns()}{result.spell}.png"
                            sample = cv2.resize(gesture, (SAMPLE_SIZE, SAMPLE_SIZE))
                            training_dir.mkdir(parents=True, exist_ok=True)
                            if not cv2.imwrite(str(training_dir / filename), sample):
                                logger.warning("Could not save camera training example")
                        if result.spell != "mistakes":
                            hass.TriggerAutomation(f"automation.wand_{result.spell}")
                    except (ProcessingError, OSError) as exc:
                        logger.warning("Camera spell failed: %s", exc)
                if show_windows:
                    cv2.imshow("Output", gesture)
            if args.debug_fps == "True":
                frame_count += 1
                now = time.monotonic()
                if now >= report_at:
                    logger.info("Processed %d camera frames in the last second", frame_count)
                    frame_count, report_at = 0, now + 1
            if show_windows and cv2.waitKey(1) == 27:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if capture is not None:
            capture.release()
        if uploader:
            uploader.shutdown()
        if show_windows:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
