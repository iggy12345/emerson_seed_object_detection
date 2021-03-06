from multiprocessing import Process, Queue
import time
import numpy as np
import traceback
import sys

from dependencies.queue_ops import lossy_enqueue


class CameraServer(Process):
    """Represents a Camera that places it's frames into a Queue object passed in at startup."""

    def __init__(self, cam_type, data_q: Queue, tx_q: Queue = None,
                 ignore_if_full: bool = True, sleep_if_full: bool = True,
                 filename: str = "", configuration_file: str = ""):
        super().__init__()
        self.cam = cam_type
        self.q = data_q
        self.tx_q = tx_q
        self.is_stopping = False
        self.ignore = ignore_if_full
        self.sleep = sleep_if_full
        self.filename = filename
        self.settings = configuration_file

    def join(self, **kwargs):
        """Stops the camera server"""
        self.is_stopping = True
        super().join(**kwargs)

    def run(self) -> None:
        self.cam = self.cam(self.filename, self.settings)
        self.cam.start_streams()
        self.cam.connect()
        self.cam.start_capture()

        try:
            while not self.is_stopping:
                if self.q.full() and self.sleep:
                    time.sleep(1)
                    continue
                elif self.q.full():
                    print('Purging queue')
                    while not self.q.empty():
                        try:
                            self.q.get_nowait()
                        finally:
                            break

                frames = self.cam.get_frame()
                lossy_enqueue(self.q, frames)
        finally:
            self.cam.stop_capture()
            self.cam.disconnect()


class SplitCamServer(CameraServer):
    """Same as a CameraServer, but accepts 3 Queues and places the rgb, ir, and depth into their own queues"""

    def __init__(self, cam_type,
                 rgb_q: Queue = None, rgb_resolution: tuple = (1280, 720), rgb_framerate: int = 30,
                 ir_q: Queue = None, ir_resolution: tuple = (640, 480), ir_framerate: int = 90,
                 depth_q: Queue = None, depth_resolution: tuple = (640, 480), depth_framerate: int = 90,
                 tx_q: Queue = None,
                 ignore_if_full: bool = True, sleep_if_full: bool = False,
                 filename: str = "", configuration_file: str = ""):
        super().__init__(cam_type, rgb_q, tx_q, ignore_if_full, sleep_if_full, filename, configuration_file)
        self.name = 'Cam Server'
        self.cam = cam_type

        self.rgb_q = rgb_q
        self.rgb_data = {'resolution': rgb_resolution, 'fps': rgb_framerate}

        self.ir_q = ir_q
        self.ir_data = {'resolution': ir_resolution, 'fps': ir_framerate}

        self.depth_q = depth_q
        self.depth_data = {'resolution': depth_resolution, 'fps': depth_framerate}

        self.fps = 0
        print("Creating split camera server")

    def run(self) -> None:
        try:
            self.cam = self.cam(self.filename, self.settings)

            if self.depth_q is not None:
                res = self.depth_data['resolution']
                self.cam.set_framerate(self.depth_data['fps'])
                self.cam.set_resolution(res[0], res[1])
                self.cam.start_depth_stream()

            if self.ir_q is not None:
                res = self.ir_data['resolution']
                self.cam.set_framerate(self.ir_data['fps'])
                self.cam.set_resolution(res[0], res[1])
                self.cam.start_ir_stream()

            if self.rgb_q is not None:
                res = self.rgb_data['resolution']
                self.cam.set_framerate(self.rgb_data['fps'])
                self.cam.set_resolution(res[0], res[1])
                self.cam.start_color_stream()

            # self.cam.start_streams()
            self.cam.connect()
            self.cam.start_capture()

            try:
                while not self.is_stopping:
                    if (
                            (self.rgb_q is not None and self.rgb_q.full()) or
                            (self.ir_q is not None and self.ir_q.full()) or
                            (self.depth_q is not None and self.depth_q.full())
                       ) and self.sleep:
                        time.sleep(1)
                        continue
                    elif (self.rgb_q is not None and self.rgb_q.full()) or \
                            (self.ir_q is not None and self.ir_q.full()) or \
                            (self.depth_q is not None and self.depth_q.full()):
                        if self.rgb_q is not None:
                            while not self.rgb_q.empty():
                                try:
                                    self.rgb_q.get_nowait()
                                finally:
                                    break
                        if self.ir_q is not None:
                            while not self.ir_q.empty():
                                try:
                                    self.ir_q.get_nowait()
                                finally:
                                    break
                        if self.depth_q is not None:
                            while not self.depth_q.empty():
                                try:
                                    self.depth_q.get_nowait()
                                finally:
                                    break

                    start = time.time()
                    rgb, ir, depth = self.cam.get_frame()
                    lossy_enqueue(self.rgb_q, rgb)
                    lossy_enqueue(self.ir_q, ir)
                    lossy_enqueue(self.depth_q, depth)
                    elapsed = time.time() - start
                    self.fps = (1 / elapsed) if elapsed != 0 else np.inf

                    if self.tx_q is not None:
                        self.tx_q.put(self.fps)
            finally:
                self.cam.stop_capture()
                self.cam.disconnect()
        except Exception as e:
            et, ev, tb = sys.exc_info()
            exc = "Exception was thrown: {}\n".format(e)
            for l in traceback.format_exception(et, ev, tb):
                exc += l
            print(exc)
            print("Something went wrong while trying to collect frame for the camera")
