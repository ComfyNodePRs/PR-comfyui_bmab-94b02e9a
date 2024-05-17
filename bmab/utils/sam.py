import cv2
import os
import numpy as np

from PIL import Image
from segment_anything import SamPredictor
from segment_anything import sam_model_registry
from bmab import utils


bmab_model_path = os.path.join(os.path.dirname(__file__), '../../models')

sam_model = None


def sam_init():
	MODEL_TYPE = 'vit_b'

	global sam_model
	if not sam_model:
		utils.lazy_loader('sam_vit_b_01ec64.pth')
		sam_model = sam_model_registry[MODEL_TYPE](checkpoint='%s/sam_vit_b_01ec64.pth' % bmab_model_path)
		sam_model.to(device='cuda:0')
		sam_model.eval()

	return sam_model


def sam_predict(pilimg, boxes):
	sam = sam_init()

	mask_predictor = SamPredictor(sam)

	numpy_image = np.array(pilimg)
	opencv_image = cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR)
	mask_predictor.set_image(opencv_image)

	result = Image.new('L', pilimg.size, 0)
	for box in boxes:
		x1, y1, x2, y2 = box

		box = np.array([int(x1), int(y1), int(x2), int(y2)])
		masks, scores, logits = mask_predictor.predict(
			box=box,
			multimask_output=False
		)

		mask = Image.fromarray(masks[0])
		result.paste(mask, mask=mask)

	return result


def sam_predict_box(pilimg, box):
	sam = sam_init()

	mask_predictor = SamPredictor(sam)

	numpy_image = np.array(pilimg)
	opencv_image = cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR)
	mask_predictor.set_image(opencv_image)

	x1, y1, x2, y2 = box
	box = np.array([int(x1), int(y1), int(x2), int(y2)])

	masks, scores, logits = mask_predictor.predict(
		box=box,
		multimask_output=False
	)

	return Image.fromarray(masks[0])


def release():
	global sam_model
	sam_model = None
	utils.torch_gc()
