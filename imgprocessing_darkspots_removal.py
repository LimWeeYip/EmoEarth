import cv2
import numpy as np
import os

input_dir = "frames_filled"
output_dir = "frames_filled_cleaned"
os.makedirs(output_dir, exist_ok=True)

#---------------------------
# Function to remove noises
#---------------------------
def cleaning(input_img, output_img):
    image = cv2.imread(input_img)

    h, w, _ = image.shape

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY_INV)

    #Exclude date box processing - Need to modify earlier pipeline to add the datebox after this section
    box_h = int(h * 0.12)
    box_w = int(w * 0.15)
    mask[0:box_h, 0:box_w] = 0
    #-----------

    # Defining kernel to replace noises by blending neighbouring pixels
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    result = cv2.inpaint(image, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

    cv2.imwrite(output_img, result)

#---------------------------
# Testing...
#---------------------------
# input_img = os.path.join(input_dir, '2026-01-19.png')
# output_img = os.path.join(output_dir, '2026-01-19_v2.png')


#---------------------------
# Loop through all images in folder
#---------------------------
for file in os.listdir(input_dir):
    if file.lower().endswith(".png"):
        input_img = os.path.join(input_dir, file)
        output_img = os.path.join(output_dir, file)
        
        cleaning(input_img, output_img)