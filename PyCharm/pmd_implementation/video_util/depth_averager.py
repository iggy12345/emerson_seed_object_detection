import matplotlib.pyplot as plt
from video_util.argparse_util import get_parser_options
import math
from video_util.collection_util import get_camera, DepthListener
from collections import deque
import numpy as np

# Required import, registers '3d' projection
from mpl_toolkits.mplot3d import Axes3D

import matplotlib.widgets as widg
from matplotlib.path import Path as pth
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
import time
import cv2


class Point:

    ref_point = None

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __str__(self):
        return "({}, {})".format(self.x, self.y)

    def mag(self):
        """Returns the magnitude of this point with respect to either the origin or the given reference"""

        if Point.ref_point is not None and isinstance(Point.ref_point, self.__class__):
            return math.sqrt((self.x - Point.ref_point.x)**2 + (self.y - Point.ref_point.y)**2)
        else:
            return math.sqrt(self.x**2 + self.y**2)

    def angle(self):
        """Returns the angle of this point with respect to either the origin or the given reference"""

        if Point.ref_point is not None and isinstance(Point.ref_point, self.__class__):
            return math.atan((Point.ref_point.y - self.y) / (Point.ref_point.x - self.x))
        else:
            return math.atan(self.y / self.x)

    def __eq__(self, other):
        if other is not None and isinstance(other, self.__class__):
            return other.x == self.x and other.y == self.y
        else:
            return False

    def __lt__(self, other):
        if other is not None and isinstance(other, self.__class__):
            if self.y == 0 and self.x > 0:
                return True
            elif other.y == 0 and other.x > 0:
                return False
            elif self.y > 0 > other.y:
                return True
            elif self.y < 0 < other.y:
                return False
            else:
                return self.x * other.y - self.y * other.x
        else:
            return False

    def __gt__(self, other):
        return not (self == other or self < other)


class SelectFromCollection(object):
    """Select indices from a matplotlib collection using `PolygonSelector`.

    Selected indices are placed into the xys as a series of Point objects for plotting later
    """

    def __init__(self, ax):
        self.xys = []
        self.ax = ax
        self.poly = widg.PolygonSelector(ax, self.onselect, lineprops={'color': 'r', 'linestyle': '-'})

    def onselect(self, verts):
        global roi
        print("Selection: ", verts)
        self.xys = verts[:]
        roi = True

    def disconnect(self):
        self.poly.disconnect_events()


def get_mask(verts, current_image):
    ny, nx = np.shape(current_image)
    # Create vertex coordinates for each grid cell...
    # (<0,0> is at the top left of the grid in this system)
    x, y = np.meshgrid(np.arange(nx), np.arange(ny))
    x, y = x.flatten(), y.flatten()
    points = np.vstack((x, y)).T

    roi_path = pth(verts)
    grid = roi_path.contains_points(points).reshape((ny, nx))

    return grid


def draw_3d_scatter(ax, depths, h: int, w: int, validator, interpolation: int = 10):
    """Creates 3 arrays of points the correspond to valid depth points on the image,
    then plots them onto the given axis"""

    x = []
    y = []
    z = []

    # filters the depth image for only valid points and those that have depths > 0
    for r in range(0, w, interpolation):
        for c in range(0, h, interpolation):
            if validator(r, c) and depths[r][c] != 0:
                x.append(width - r)
                y.append(c)
                z.append(depth_image[r][c])

    # Plots the points
    ax.scatter(y, x, z, c=z, cmap='plasma', vmin=0, vmax=max(z))


if __name__ == "__main__":

    # region Setup

    # region Argument parsing and input collection

    parser = get_parser_options("File for find the average depth of a section of a video captured by the camera")
    parser.add_argument("--filename", '-f', type=str, default="", required=False)
    parser.add_argument("--region", '-r', type=str, default="", required=False, help="""To specify the region, simply type in a series of integers with a space separating them
    For rectangle: each int represents the rectangle corners in the order top right bottom left
    For freeform: each set of two ints represents a coordinate of the polygon""")
    parser.add_argument("--shape", '-s', type=str, default="", choices=["", "rectangle", "freeform"], required=False)

    args = parser.parse_args()

    if args.filename == "":
        filename = input("File to analyze? ")
    else:
        filename = args.filename

    region = args.region
    shape = args.shape
    roi = args.region != "" and args.shape == "rectangle" or args.shape == "freeform"

    # endregion

    # region Opens rrf file and sets up camera

    cap = get_camera(args, filename)
    # cap.setUseCase("MODE_5_45FPS_500")
    # cap.setExposureTime(150)

    # endregion

    # region Hooks up the queues

    q = deque()
    q_depth = deque()
    l_depth = DepthListener(q, q_depth)
    cap.registerDataListener(l_depth)

    # endregion

    # Starts playback
    cap.startCapture()

    # region Prepares plt window

    plt.ion()

    disp = plt.figure(figsize=[10, 5])

    ax = disp.add_subplot(121)

    dmp = disp.add_subplot(122, projection='3d')
    dmp.set_zlim([0, 5])

    disp.subplots_adjust(bottom=0.2)

    # endregion

    # region Sets up callbacks for the buttons

    clicked = False
    stopping = False
    poly = None

    def click(something):
        global clicked
        clicked = True

    def stop(something):
        global stopping
        stopping = True

    # endregion

    # region Sets up the buttons

    dimensions = [0.7, 0.05, 0.1, 0.075]

    # region Sets up the ROI button

    but_ax = plt.axes(arg=dimensions)
    but = widg.Button(but_ax, 'ROI')
    but.on_clicked(click)

    # endregion

    # region Sets up the stop button

    dimensions[0] = 0.59
    another_ax = plt.axes(arg=dimensions)
    but2 = widg.Button(another_ax, 'STOP')
    but2.on_clicked(stop)

    # endregion

    # Draws the buttons onto the canvas initially
    plt.show(block=False)

    # endregion

    # endregion

    while cap.isConnected():
        frame = None
        depth_image = None
        if len(q) > 0 and len(q_depth) > 0:

            # region Camera frame collection and management

            frame = q.pop()
            depth_image = q_depth.pop()

            if len(q) > 25 or len(q_depth) > 25:
                print("video running behind, clearing queues")
                q.clear()
                q_depth.clear()

            # endregion

            # Sleeps after frame collection to allow next frame to be developed
            time.sleep(0.05)

            # region Resets the painting canvas

            ax.clear()
            dmp.clear()

            # endregion

            # region Paints the grayscale image to the screen

            # # Draw rgb image
            # image = np.stack((frame,)*3, axis=-1)
            # # print(image)
            try:
                # img = Image.fromarray(image)
                ax.pcolormesh(frame, cmap='gray')
                ax.invert_yaxis()
            except Exception as e:
                print(e)

            # endregion

            #  region Plots the 3d scatter plot of the depth image

            # Collects the width and height of the image
            width, height = np.shape(depth_image)

            if roi:
                # region Handles the case that there is an ROI active

                # region Plots the lines surrounding the ROI

                x_coord = [x[0] for x in region.verts]
                y_coord = [y[1] for y in region.verts]

                # Checks if there were any vertices in the ROI, if not, skip this and reset
                if len(x_coord) == 0:
                    print("Resetting ROI")
                    roi = False
                    continue

                # Re-plots the lasso
                ax.plot(x_coord + [x_coord[0]], y_coord + [y_coord[0]], 'r')

                # endregion

                # Crops the selected region
                crop = get_mask(region.verts, depth_image)

                # region Selects the points in the ROI that have a depth > 0

                selection = []
                for row in range(width):
                    for p in range(height):
                        if crop[row][p] and depth_image[row][p] != 0:
                            x_coord.append(row)
                            y_coord.append(height - p)
                            selection.append(depth_image[row][p])

                # endregion

                # Calculates the average depth
                m = sum(selection) / len(selection) if len(selection) > 0 else 0

                # region Prints the average depth text

                min_x = min(x_coord)
                max_x = max(x_coord)
                min_y = min(y_coord)
                max_y = max(y_coord)

                # prints the average depth text
                ax.text((max_x - min_x) / 2 + min_x - 50,
                        (max_y - min_y) / 2 + min_y,
                        "Average depth: {}".format(round(m, 1)), fontdict={"color": 'r', "backgroundcolor": 'k'})

                # Plots the point cloud, but only for points in the ROI
                draw_3d_scatter(dmp, depth_image, height, width, lambda r, c: crop[r][c], 3)

                # endregion

                # region Sets the axis limits on the 3d plot so that the image doesn't jump around as much

                dmp.set_xlim([min_y, max_y])
                dmp.set_zlim([0, 5])
                dmp.set_ylim([min_x, max_x])

                # endregion

            else:
                # Plots the point cloud
                draw_3d_scatter(dmp, depth_image, height, width, lambda r, c: True)

                # region Code for creating a surface instead of points

                # y_coord = np.arange(0, width, 1)
                # x_coord = np.arange(height, 0, -1)
                #
                # x_coord, y_coord = np.meshgrid(x_coord, y_coord)
                #
                # dmp.plot_surface(x_coord, y_coord, depth_image,
                #                  cmap=cm.coolwarm, linewidth=0, antialiased=False)

                # endregion

                # region Sets the axis limits on the 3d plot so that the image doesn't jump around as much

                dmp.set_xlim([0, height])
                dmp.set_zlim([0, 5])
                dmp.set_ylim([0, width])

                # endregion

            # endregion

            # region Repaints the window

            dmp.invert_zaxis()

            plt.draw()
            plt.pause(0.001)

            # endregion

        else:
            time.sleep(0.5)
            continue

        # region Checks if the ROI button was pressed

        if clicked:
            clicked = False
            print("Choose a ROI by clicking on the screen")
            print("Use Ctrl to adjust vertices, and Shift to move the image")
            print("Press Esc to erase the current ROI")
            print("When you are ready, click on 'ROI' again to continue")
            poly = SelectFromCollection(ax)

            # # Waits for the user to select a new ROI
            # while not clicked:
            #     plt.draw()
            #     plt.pause(0.001)

            region = poly.poly
            roi = True
            # clicked = False

        # endregion

        # region Checks if the STOP button was pressed

        if stopping:
            break

        # endregion

    cap.stopCapture()
    plt.close(disp)



