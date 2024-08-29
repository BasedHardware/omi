import base64
import json
import os

import cv2
from fastapi import APIRouter

from models import Memory, EndpointResponse

router = APIRouter()


def count_faces(image_path):
    # Load the pre-trained face detection model
    model_file = "advanced/models/opencv_face_detector_uint8.pb"
    config_file = "advanced/models/opencv_face_detector.pbtxt"
    net = cv2.dnn.readNetFromTensorflow(model_file, config_file)

    # Read the image
    image = cv2.imread(image_path)

    # Get image dimensions
    (h, w) = image.shape[:2]

    # Create a blob from the image
    blob = cv2.dnn.blobFromImage(image, 1.0, (300, 300), [104, 117, 123], False, False)

    # Set the blob as input to the network
    net.setInput(blob)

    # Run forward pass to get output of the output layers
    detections = net.forward()

    # Initialize the count of faces
    face_count = 0

    # Loop over the detections
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]

        # Filter out weak detections by ensuring the confidence is greater than a minimum confidence
        if confidence > 0.5:
            face_count += 1

    return face_count


@router.post('/openglass', tags=['advanced', 'openglass'], response_model=EndpointResponse)
def open_glass_example(memory: Memory, uid: str):
    if not memory.photos:
        return {}

    print(json.dumps(memory.dict(), indent=2, default=str))
    directory = f'tmp/{uid}'
    os.makedirs(directory, exist_ok=True)

    total_faces = 0
    for i, photo in enumerate(memory.photos):
        path = f'{directory}/photo_{i}.png'
        with open(path, "wb") as f:
            try:
                f.write(base64.decodebytes(photo.base64.encode()))
            except Exception as e:
                print(f'Error decoding base64: {e}')
            total_faces += count_faces(path)

    return {'message': f'Total faces detected: {total_faces}'}
