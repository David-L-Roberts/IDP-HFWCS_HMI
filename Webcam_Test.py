#!/usr/bin/env python3
import asyncio
import base64
import concurrent.futures
import signal
import time

import cv2
import numpy as np
from fastapi import Response

import nicegui.globals
from nicegui import app, ui

# refresh period of webcam feed, in seconds
FRAME_REFRESH_T = 0.05

STATIC_IMG_PATH = "D:/1. My Folders/Programming/Python/100_Uni_Projects/01_HFWCS_HMI/HFWCS_HMI-v0.0.1/Resources/Empty_Transparent.png"

# We need an executor to schedule CPU-intensive tasks with `loop.run_in_executor()`.
process_pool_executor = concurrent.futures.ProcessPoolExecutor()
# In case you don't have a webcam, this will provide a black placeholder image.
black_1px = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAAXNSR0IArs4c6QAAAA1JREFUGFdjYGBg+A8AAQQBAHAgZQsAAAAASUVORK5CYII='
placeholder = Response(content=base64.b64decode(black_1px.encode('ascii')), media_type='image/png')
# OpenCV is used to access the webcam.
video_capture = cv2.VideoCapture(0)


def convert(frame: np.ndarray) -> bytes:
    _, imencode_image = cv2.imencode('.jpg', frame)
    return imencode_image.tobytes()


@app.get('/video/frame')
# Thanks to FastAPI's `app.get`` it is easy to create a web route which always provides the latest image from OpenCV.
async def grab_video_frame() -> Response:
    if not video_capture.isOpened():
        return placeholder
    loop = asyncio.get_running_loop()
    # The `video_capture.read` call is a blocking function.
    # So we run it in a separate thread (default executor) to avoid blocking the event loop.
    _, frame = await loop.run_in_executor(None, video_capture.read)
    if frame is None:
        return placeholder
    # `convert` is a CPU-intensive function, so we run it in a separate process to avoid blocking the event loop and GIL.
    jpeg = await loop.run_in_executor(process_pool_executor, convert, frame)
    return Response(content=jpeg, media_type='image/jpeg')

with ui.element('div').classes("w-full h-[95vh] bg-slate-900 relative"):
    with ui.element('div').classes('w-full h-[95vh] absolute'):
        # For non-flickering image updates an interactive image is much better than `ui.image()`.
        video_image = ui.interactive_image().classes('w-full h-full absolute-center')
        video_image.style("max-width: 1500px")

    with ui.element('div').classes('w-full h-[95vh] absolute'):
        static_image = ui.interactive_image(STATIC_IMG_PATH, cross=True).classes('absolute-center')
        static_image.style("max-width: 1500px")

# A timer constantly updates the source of the image.
# Because data from same paths are cached by the browser,
# we must force an update by adding the current timestamp to the source.
ui.timer(interval=FRAME_REFRESH_T, callback=lambda: video_image.set_source(f'/video/frame?{time.time()}'))


async def disconnect() -> None:
    """Disconnect all clients from current running server."""
    for client in nicegui.globals.clients.keys():
        await app.sio.disconnect(client)


def handle_sigint(signum, frame) -> None:
    # `disconnect` is async, so it must be called from the event loop; we use `ui.timer` to do so.
    ui.timer(0.1, disconnect, once=True)
    # Delay the default handler to allow the disconnect to complete.
    ui.timer(1, lambda: signal.default_int_handler(signum, frame), once=True)


async def cleanup() -> None:
    # This prevents ugly stack traces when auto-reloading on code change,
    # because otherwise disconnected clients try to reconnect to the newly started server.
    await disconnect()
    # Release the webcam hardware so it can be used by other applications again.
    video_capture.release()
    # The process pool executor must be shutdown when the app is closed, otherwise the process will not exit.
    process_pool_executor.shutdown()

app.on_shutdown(cleanup)
# We also need to disconnect clients when the app is stopped with Ctrl+C,
# because otherwise they will keep requesting images which lead to unfinished subprocesses blocking the shutdown.
signal.signal(signal.SIGINT, handle_sigint)

ui.run(port=11_000, dark=True, native=True, window_size=(1920, 1080))