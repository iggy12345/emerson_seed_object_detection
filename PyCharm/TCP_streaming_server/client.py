import socket
import numpy as np
import matplotlib.pyplot as plt
import time
import json
from multiprocessing import Process

from server_util.datapacket_util import VideoStreamDatagram, VideoInitDatagram


host = 'localhost'
buffsize = 3072000
residual_data = ''


def readline(sock: socket.socket) -> str:
    """Continuously calls read on the given socket until a '\n' is found,
    then saves the residual and returns the string"""

    global residual_data

    if '\n' in residual_data:
        index = residual_data.find('\n')

        temp = residual_data[:index]

        if index < len(residual_data) - 1:
            residual_data = residual_data[index + 1:]
        else:
            residual_data = ''

        return temp

    result = residual_data

    data_read = sock.recv(buffsize).decode('utf-8')
    while data_read != '' and '\n' not in data_read:
        result += data_read
        data_read = sock.recv(buffsize).decode('utf-8')

    if data_read != '':
        index = data_read.find('\n')
        result += data_read[:index]
        if index < len(data_read) - 1:
            residual_data = data_read[index + 1:]
        else:
            residual_data = ''

    return result


def frame_socket(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))

        streams = None
        framedata = None
        iteration = 0

        first = True
        while True:
            iteration += 1

            data = readline(sock)

            if data != '':
                if first:
                    first = False
                    streams = VideoInitDatagram.from_json(data)
                else:
                    try:
                        framedata = VideoStreamDatagram.from_json(data)
                    except json.decoder.JSONDecoderError as e:
                        print(e)
                        print("Detecting incomplete frame, skipping")
                        continue

                if framedata is not None:
                    if framedata.name == 'rgb':
                        res = streams.streams[0].resolution
                        rgb_frame = np.reshape(framedata.frame, newshape=(res[1], res[0]))

                        plt.clf()
                        plt.imshow(rgb_frame)
                        plt.draw()
                        plt.pause(0.001)
                    if framedata.name == 'ir':
                        res = streams.streams[0].resolution
                        ir_frame = np.reshape(framedata.frame, newshape=(res[1], res[0]))

                        plt.clf()
                        plt.imshow(ir_frame)
                        plt.draw()
                        plt.pause(0.001)
                    if framedata.name == 'depth':
                        res = streams.streams[0].resolution
                        depth_frame = np.reshape(framedata.frame, newshape=(res[1], res[0]))
                        depth_frame = np.multiply(depth_frame, 1 / depth_frame.max())

                        plt.clf()
                        plt.imshow(depth_frame)
                        plt.draw()
                        plt.pause(0.001)


if __name__ == '__main__':
    processes = [
                    Process(target=frame_socket, args=(int(input('RGB Port Number: ')),)),
                    Process(target=frame_socket, args=(int(input('Depth Port Number: ')),)),
                ]

    for p in processes:
        p.start()

    for p in processes:
        p.join()
