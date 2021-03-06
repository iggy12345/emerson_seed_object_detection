# -*- coding: utf-8 -*-
# pylint: disable=C0103
# pylint: disable=E1101

print('Importing libraries')
import sys
import time
import numpy as np
import tensorflow as tf
import cv2
from random import *
import argparse

from utils import label_map_util
from utils import visualization_utils_color as vis_util
from utils import vis_depth_util
from utils.model_util import TensorflowFaceDetector

from roypy_util import roypy
from collections import deque
from roypy_util.sample_camera_info import print_camera_info
from roypy_util.roypy_sample_utils import CameraOpener, add_camera_opener_options
from roypy_util.roypy_platform_utils import PlatformHelper
from roypy_util.roypy_classes import *

# Parser info
parser = argparse.ArgumentParser(description="Used to take live video using the roypy camera.", usage=__doc__)
add_camera_opener_options (parser)
options = parser.parse_args()

# pmd software utillity stuff
platformhelper = PlatformHelper()
opener = CameraOpener (options)
cap = opener.open_camera ()

print('Setting up paths')
# Path to frozen detection graph. This is the actual model that is used for the object detection.
PATH_TO_CKPT = './models/frozen_graph/frozen_inference_graph.pb'

# List of the strings that is used to add correct label for each box.
PATH_TO_LABELS = './protos/seed_label_map.pbtxt'

NUM_CLASSES = 2

print('Loading labelmaps')
label_map = label_map_util.load_labelmap(PATH_TO_LABELS)
categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=NUM_CLASSES, use_display_name=True)
category_index = label_map_util.create_category_index(categories)

print_camera_info (cap)
print("isConnected", cap.isConnected())
print("getFrameRate", cap.getFrameRate())

if __name__ == "__main__":
    import sys
    tDetector = TensorflowFaceDetector(PATH_TO_CKPT)

    # we will use this queue to synchronize the callback with the main
    # thread, as drawing should happen in the main thread
    q = deque()
    q_depth = deque()
    l = ImageListener(q)
    l_depth = DepthListener(q_depth)
    cap.registerIRImageListener(l)
    cap.registerDataListener(l_depth)
    cap.setUseCase("MODE_5_45FPS_500")
    #cap.setExposureMode(MANUAL)
    cap.setExposureTime(80)
    print(cap.getCurrentUseCase())
    cap.startCapture()

    print('Starting computation')
    windowNotSet = True
    while cap.isConnected():
        frame = None
        depth_frame = None
        # Collect the next frame if it's ready
        if len(q) > 0 and len(q_depth) > 0:
            frame = q.pop()
            depth_frame = q_depth.pop()
        else:
            # Otherwise sleep for 20 ms, guaranteeing a new frame next time
            time.sleep(0.2)
            continue
            
        if frame is not None and depth_frame is not None:
            image = np.stack((frame,)*3, axis=-1)

            [h, w] = image.shape[:2]
            #print (h, w)
            # image = cv2.flip(image, 1)

            (boxes, scores, classes, num_detections) = tDetector.run(image)

            # Draws bounding boxes
            vis_util.visualize_boxes_and_labels_on_image_array(
                image,
                np.squeeze(boxes),
                np.squeeze(classes).astype(np.int32),
                np.squeeze(scores),
                category_index,
                use_normalized_coordinates=True,
                line_thickness=4)

            # Draws the depth information
            vis_depth_util.apply_depth_to_boxes(image, np.squeeze(boxes), np.squeeze(scores), profile, depth_frame)

            if windowNotSet is True:
                cv2.namedWindow("tensorflow based (%d, %d)" % (w, h), cv2.WINDOW_NORMAL)
                windowNotSet = False

            # This is the depth scale stuff, it can also be found in
            # apply_depth_to_boxes
            depth_image = np.stack((depth_frame,)*3, axis=-1)
            sel_y = randint(0, depth_image.shape[0] - 1)
            sel_x = randint(0, depth_image.shape[1] - 1)
            depth_image_scaled = cv2.convertScaleAbs(depth_image, alpha=0.03) #depth_scale)
            depth_colormap = cv2.applyColorMap(depth_image_scaled, cv2.COLORMAP_JET)
            image = np.hstack((image, depth_colormap))

            cv2.imshow("tensorflow based (%d, %d)" % (w, h), image)
        k = cv2.waitKey(1) & 0xff
        if k == ord('q') or k == 27:
            break
        input('Press any key to continue...')

    cap.stopCapture()
    cv2.destroyAllWindows()
