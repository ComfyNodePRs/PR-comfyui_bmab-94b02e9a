import comfy
import nodes
import folder_paths
from bmab import utils
from bmab.nodes.binder import BMABBind
from bmab.nodes.binder import BMABLoraBind
from bmab.external.advanced_clip import advanced_encode


class BMABIntegrator:
	@classmethod
	def INPUT_TYPES(s):
		return {
			'required': {
				'model': ('MODEL',),
				'clip': ('CLIP',),
				'vae': ('VAE',),
				'seed': ('INT', {'default': 0, 'min': 0, 'max': 0xffffffffffffffff}),
				'stop_at_clip_layer': ('INT', {'default': -2, 'min': -24, 'max': -1, 'step': 1}),
				'token_normalization': (['none', 'mean', 'length', 'length+mean'],),
				'weight_interpretation': (['original', 'comfy', 'A1111', 'compel', 'comfy++', 'down_weight'],),
				'prompt': ('STRING', {'multiline': True, 'dynamicPrompts': True}),
				'negative_prompt': ('STRING', {'multiline': True, 'dynamicPrompts': True}),
			},
			'optional': {
				'seed_in': ('SEED',),
				'latent': ('LATENT',),
				'image': ('IMAGE',),
			}
		}

	RETURN_TYPES = ('BMAB bind', 'SEED')
	RETURN_NAMES = ('BMAB bind', 'seed',)
	FUNCTION = 'integrate_inputs'

	CATEGORY = 'BMAB/sampler'

	def integrate_inputs(self, model, clip, vae, seed, stop_at_clip_layer, token_normalization, weight_interpretation, prompt, negative_prompt, seed_in=None, latent=None, image=None, ):

		if seed_in is not None:
			seed = seed_in

		prompt = utils.parse_prompt(prompt, seed)

		if weight_interpretation == 'original':
			tokens = clip.tokenize(prompt)
			cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
			positive = [[cond, {'pooled_output': pooled}]]
			tokens = clip.tokenize(negative_prompt)
			cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
			negative = [[cond, {'pooled_output': pooled}]]
		else:
			embeddings_final, pooled = advanced_encode(clip, prompt, token_normalization, weight_interpretation, w_max=1.0, apply_to_pooled=False)
			positive = [[embeddings_final, {'pooled_output': pooled}]]
			embeddings_final, pooled = advanced_encode(clip, negative_prompt, token_normalization, weight_interpretation, w_max=1.0, apply_to_pooled=False)
			negative = [[embeddings_final, {'pooled_output': pooled}]]

		clip.clip_layer(stop_at_clip_layer)

		return BMABBind(model, clip, vae, prompt, negative_prompt, positive, negative, latent, seed, image), seed


class BMABExtractor:
	@classmethod
	def INPUT_TYPES(s):
		return {
			'required': {
				'bind': ('BMAB bind',),
			},
		}

	RETURN_TYPES = ('MODEL', 'CONDITIONING', 'CONDITIONING', 'VAE', 'LATENT', 'IMAGE', 'SEED')
	RETURN_NAMES = ('model', 'positive', 'negative', 'vae', 'latent', 'image', 'seed')
	FUNCTION = 'extract'

	CATEGORY = 'BMAB/sampler'

	def extract(self, bind: BMABBind):
		if bind.pixels is not None:
			t = bind.vae.encode(bind.pixels)
			bind.latent_image = {'samples': t}
		return bind.model, bind.positive, bind.negative, bind.vae, bind.latent_image, bind.pixels, bind.seed,


class BMABSeedGenerator:
	@classmethod
	def INPUT_TYPES(s):
		return {
			'required': {
				'seed': ('INT', {'default': 0, 'min': 0, 'max': 0xffffffffffffffff}),
			}
		}

	RETURN_TYPES = ('SEED',)
	RETURN_NAMES = ('seed',)
	FUNCTION = 'generate'

	CATEGORY = 'BMAB/sampler'

	def generate(self, seed):
		return seed,


class BMABKSampler:
	@classmethod
	def INPUT_TYPES(s):
		return {
			'required': {
				'bind': ('BMAB bind',),
				'steps': ('INT', {'default': 20, 'min': 1, 'max': 10000}),
				'cfg': ('FLOAT', {'default': 8.0, 'min': 0.0, 'max': 100.0, 'step': 0.1, 'round': 0.01}),
				'sampler_name': (comfy.samplers.KSampler.SAMPLERS,),
				'scheduler': (comfy.samplers.KSampler.SCHEDULERS,),
				'denoise': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 1.0, 'step': 0.01}),
			},
			'optional': {
				'lora': ('BMAB lora',)
			}
		}

	RETURN_TYPES = ('BMAB bind', 'IMAGE',)
	RETURN_NAMES = ('BMAB bind', 'image',)
	FUNCTION = 'sample'

	CATEGORY = 'BMAB/sampler'

	def load_lora(self, model, clip, lora_name, strength_model, strength_clip):
		print(f'Loading lora {lora_name}')
		lora_path = folder_paths.get_full_path('loras', lora_name)
		lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
		model_lora, clip_lora = comfy.sd.load_lora_for_models(model, clip, lora, strength_model, strength_clip)
		return (model_lora, clip_lora)

	def sample(self, bind: BMABBind, steps, cfg, sampler_name, scheduler, denoise=1.0, lora: BMABLoraBind = None):
		print('Sampler SEED', bind.seed, bind.model)
		if lora is not None:
			for l in lora.loras:
				bind.model, bind.clip = self.load_lora(bind.model, bind.clip, *l)
		samples = nodes.common_ksampler(bind.model, bind.seed, steps, cfg, sampler_name, scheduler, bind.positive, bind.negative, bind.latent_image, denoise=denoise)[0]
		bind.pixels = bind.vae.decode(samples['samples'])
		return bind, bind.pixels,


class BMABKSamplerHiresFix:
	@classmethod
	def INPUT_TYPES(s):
		return {
			'required': {
				'bind': ('BMAB bind',),
				'steps': ('INT', {'default': 20, 'min': 1, 'max': 10000}),
				'cfg': ('FLOAT', {'default': 4.0, 'min': 0.0, 'max': 100.0, 'step': 0.1, 'round': 0.01}),
				'sampler_name': (comfy.samplers.KSampler.SAMPLERS,),
				'scheduler': (comfy.samplers.KSampler.SCHEDULERS,),
				'denoise': ('FLOAT', {'default': 0.4, 'min': 0.0, 'max': 1.0, 'step': 0.01}),
			},
			'optional': {
				'image': ('IMAGE',),
				'lora': ('BMAB lora',)
			}
		}

	RETURN_TYPES = ('BMAB bind', 'IMAGE',)
	RETURN_NAMES = ('BMAB bind', 'image',)
	FUNCTION = 'sample'

	CATEGORY = 'BMAB/sampler'

	def load_lora(self, model, clip, lora_name, strength_model, strength_clip):
		print(f'Loading lora {lora_name}')
		lora_path = folder_paths.get_full_path('loras', lora_name)
		lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
		model_lora, clip_lora = comfy.sd.load_lora_for_models(model, clip, lora, strength_model, strength_clip)
		return (model_lora, clip_lora)

	def sample(self, bind: BMABBind, steps, cfg, sampler_name, scheduler, denoise=1.0, image=None, lora: BMABLoraBind = None):
		pixels = bind.pixels if image is None else image
		print('Hires SEED', bind.seed, bind.model)
		latent = dict(samples=bind.vae.encode(pixels))
		if lora is not None:
			for l in lora.loras:
				bind.model, bind.clip = self.load_lora(bind.model, bind.clip, *l)
		samples = nodes.common_ksampler(bind.model, bind.seed, steps, cfg, sampler_name, scheduler, bind.positive, bind.negative, latent, denoise=denoise, force_full_denoise=True)[0]
		bind.pixels = bind.vae.decode(samples['samples'])
		return bind, bind.pixels,


class BMABPrompt:
	@classmethod
	def INPUT_TYPES(s):
		return {
			'required': {
				'bind': ('BMAB bind',),
				'text': ('STRING', {'multiline': True, 'dynamicPrompts': True}),
				'token_normalization': (['none', 'mean', 'length', 'length+mean'],),
				'weight_interpretation': (['original', 'comfy', 'A1111', 'compel', 'comfy++', 'down_weight'],),
			}
		}

	RETURN_TYPES = ('BMAB bind',)
	RETURN_NAMES = ('bind', )
	FUNCTION = 'prompt'

	CATEGORY = 'BMAB/sampler'

	def prompt(self, bind: BMABBind, text, token_normalization, weight_interpretation):

		bind = bind.copy()
		bind.prompt = text
		bind.clip = bind.clip.clone()
		prompt = utils.parse_prompt(bind.prompt, bind.seed)

		if weight_interpretation == 'original':
			tokens = bind.clip.tokenize(prompt)
			cond, pooled = bind.clip.encode_from_tokens(tokens, return_pooled=True)
			bind.positive = [[cond, {'pooled_output': pooled}]]
		else:
			embeddings_final, pooled = advanced_encode(bind.clip, prompt, token_normalization, weight_interpretation, w_max=1.0, apply_to_pooled=False)
			bind.positive = [[embeddings_final, {'pooled_output': pooled}]]

		return (bind, )