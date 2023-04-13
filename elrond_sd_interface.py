import base64
import json
import random
import aiohttp
from dotenv import dotenv_values

config = dotenv_values(".env")
debug_mode = bool(config["DEBUG_MODE"] == "True")
use_webui_default_prompts = bool(config["USE_WEBUI_DEFAULT_PROMPTS"] == "True")
sampling_method_txt2img = str(config["SAMPLING_METHOD_TXT2IMG"])
sampling_method_img2img = str(config["SAMPLING_METHOD_IMG2IMG"])


async def download_image_from_url(img_url: str) -> str:
    """Takes any URL and downloads the image from there, returns image data.

    Args:
        img_url: The URL to the image.

    Returns:
        The downloaded image in base64 encoding with the prefix
        "data:image/png;base64,".
    """

    image_data = ""

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(img_url) as resp:
                if resp.status == 200:
                    file = await resp.read()
                    image_data = ("data:image/png;base64," +
                                  str(base64.b64encode(file).decode("utf-8")))
        except Exception as e:
            print("Download of " + img_url + " failed: " + str(e))

    # image_data = "data:image/png;base64,ABC..."
    return image_data


async def interface_img_interrogate(
        image_data: str,
        model: str = "clip"
) -> str:
    """ Check image, generate text

    Args:
        image_data: The input image in base64 encoding inluding the prefix
            ("data:image/png;base64").
        model: Interrogation model to use. "clip" for descriptive text,
            "DeepBooru" für tags.

    Returns:
        The descriptive text resulting from the image interrogation.
    """

    print("Interrogating.")
    host = config["GRADIO_API_BASE_URL"]

    request = {
        "image": image_data,
        "model": model,
    }
    image_description = None

    async with aiohttp.ClientSession() as session:
        async with (session.post(host + "/sdapi/v1/interrogate", json=request)
                    as response):
            response_json = await response.json()

            if debug_mode:
                with open(".debug.interrogate_image.json", "w",
                          encoding="utf-8") as f:
                    json.dump(response_json, f, ensure_ascii=False, indent=4)

            image_description = response_json["caption"]

    return image_description


async def interface_interrogate_url(
        img_url: str,
        model: str = "clip"
) -> str | None:
    """Returns interrogation description of an image specified by URL.

    Args:
        img_url: The URL pointing to the image to be interrogated.
        model: Interrogation model to use. "clip" for descriptive text,
            "DeepBooru" für tags.

    Returns:
        The descriptive text resulting from the image interrogation.
    """

    print("Downloading " + img_url)
    image_data = await download_image_from_url(img_url)

    if image_data != "":
        return await interface_img_interrogate(image_data, model)
    else:
        return None


async def interface_upscale_image(
        encoded_image: str,
        size: int = 2,
        upscaler: str = "SwinIR_4x"
) -> str:
    """Returns upscaled version of a given image.

    Upscales the image given in base64 encoding using the given upscaler
    with the given size factor, returning the upscaled image encoded
    in base64.

    Args:
        encoded_image: The input image in base64 encoding inluding the prefix
            ("data:image/png;base64").
        quantity: The factor by which to upscale the image's dimensions.
        upscaler: The upscaling algorithm to use. Must be supported by
            the machine hosting the AI model.

    Returns:
        The upscaled image in base64 encoding with the prefix
        "data:image/png;base64,".
    """

    host = config["GRADIO_API_BASE_URL"]
    print("interface upscale_image to " +
          str(size) + " with upscaler: " + upscaler)

    # Build the request for the HTTP API
    # TODO: saner defaults - from config?
    request = {
        # "resize_mode": 0,
        # "show_extras_results": true,
        # "gfpgan_visibility": 0,
        # "codeformer_visibility": 0,
        # "codeformer_weight": 0,
        "upscaling_resize": size,
        # "upscaling_resize_w": 512,
        # "upscaling_resize_h": 512,
        # "upscaling_crop": true,
        "upscaler_1": upscaler,
        # "upscaler_2": "None",
        # "extras_upscaler_2_visibility": 0,
        # "upscale_first": false,
        "image": encoded_image
    }

    image_data = ""

    async with aiohttp.ClientSession() as session:
        async with session.post(host + "/sdapi/v1/extra-single-image",
                                json=request) as response:
            response_json = await response.json()

            if debug_mode:
                with (open(".debug.upscale_image.json", "w", encoding="utf-8")
                      as f):
                    json.dump(response_json, f, ensure_ascii=False, indent=4)

            image_data = "data:image/png;base64," + response_json["image"]

    # image_data = "data:image/png;base64,ABC..."
    return image_data


async def interface_txt2img(
        prompt: str = "",
        seed: int = -1,
        quantity: int = 1,
        negative_prompt: str = "",
        simulate_nai: bool = True,
        host: str | None = None
) -> list[str]:
    """Returns images based on the text prompt given.

    The prompt and seed are forwarded to the AI model via the API
    of its WebUI, which will return images of the amount of
    `quantity`.

    Args:
        prompt: The text prompt on which the images will be based.
        seed: The seed int which will be used to initialize the AI model.
            Different seeds will result in different images for the same
            prompt.
        quantity: How many images will be returned. If no specific seed
            is given, these will all be different. If a seed is set
            via the seed parameter, all images will necessarily be the same.
        negative_prompt: The model will attempts to avoid creating images
            that match negative_prompt.
        simulate_nai: If True, will complete user-given (negative) prompts
            with additional (negative) prompt strings used by the nai
            model checkpoint.
        host: The machine that hosts the Stable Diffusion WebUI-API which
            will be used to have that machine create the images. If no
            host is specified, the default value from the config file will
            be used.

    Returns:
        A list of strings containing base64-encoded representations of the
        images, each prefixed with the substring "data:image/png;base64,".

    TODO:
        * Unify parameter handling/defaults (empty string vs. None vs.
            negative int)
    """

    # Seed fallback
    if seed == -1:
        seed = random.randint(0, 999999999)

    print("interface txt2img for " + prompt + " /quantity: " +
          str(quantity) + " /sampler: " + sampling_method_txt2img)

    if simulate_nai:
        prompt = "masterpiece, best quality, " + prompt
        negative_prompt = ("lowres, bad anatomy, bad hands, text, error, " +
                           "missing fingers, extra digit, fewer digits, " +
                           "cropped, worst quality, low quality, " +
                           "normal quality, jpeg artifacts, signature, " +
                           "watermark, username, blurry, artist name, " +
                           negative_prompt)

    # Build the request for the HTTP API
    # TODO: saner defaults - from config?
    request = {
        "prompt": prompt,
        "seed": seed,
        "sampler_name": config["SAMPLING_METHOD_TXT2IMG"],
        "negative_prompt": negative_prompt,
        "batch_size": quantity,
        # "steps": 20,
        # "cfg_scale": 11,
        # "width": 512,
        # "height": 512,
        # "restore_faces": False,
        # "enable_hr": false,
        # "denoising_strength": 0,
        # "firstphase_width": 0,
        # "firstphase_height": 0,
        # "hr_scale": 2,
        # "hr_upscaler": "string",
        # "hr_second_pass_steps": 0,
        # "hr_resize_x": 0,
        # "hr_resize_y": 0,
        # "styles": [
        #    "string"
        # ],
        # "subseed": -1,
        # "subseed_strength": 0,
        # "seed_resize_from_h": -1,
        # "seed_resize_from_w": -1,
        # "n_iter": 1,
        # "steps": 50,
        # "cfg_scale": 7,
        # "width": 512,
        # "height": 512,
        # "restore_faces": false,
        # "tiling": false,
        # "do_not_save_samples": false,
        # "do_not_save_grid": false,
        # "eta": 0,
        # "s_churn": 0,
        # "s_tmax": 0,
        # "s_tmin": 0,
        # "s_noise": 1,
        # "override_settings": {},
        # "override_settings_restore_afterwards": true,
        # "script_args": [],
        # "script_name": "string",
        # "send_images": true,
        # "save_images": false,
        # "alwayson_scripts": {}
    }
    images = []

    async with aiohttp.ClientSession() as session:
        if host is None:
            host = config["GRADIO_API_BASE_URL"]

        # With request["send_images"] = True, the HTTP API will always return
        # the full images, base64-encoded under response["images"]
        async with (session.post(host + "/sdapi/v1/txt2img", json=request)
                    as response):
            response_json = await response.json()

            if debug_mode:
                with open(".debug.txt2img_server_local_urls.json", "w",
                          encoding="utf-8") as f:
                    json.dump(response_json, f, ensure_ascii=False, indent=4)

            for img in response_json["images"]:
                images.append("data:image/png;base64," + img)

    """images =  [
        "data:image/png;base64,ABC...",
        "data:image/png;base64,ABC...",
        ...
    ]
    """
    return images


async def interface_img2img(
        prompt: str = "",
        seed: int = -1,
        quantity: int = 1,
        negative_prompt: str = "",
        simulate_nai: bool = True,
        img2img_image_data: str = "",
        denoising_strength: float = 0.6,
        host: str = None
) -> list[str]:
    """Returns images based on the input image given.

    The input image, prompt and seed are forwarded to the AI model
    via the API of its WebUI, which will return images of the amount of
    `quantity`.

    Args:
        prompt: The text prompt on which the images will be based.
        seed: The seed int which will be used to initialize the AI model.
            Different seeds will result in different images for the same
            prompt.
        quantity: How many images will be returned. If no specific seed
            is given, these will all be different. If a seed is set
            via the seed parameter, all images will necessarily be the same.
        negative_prompt: The model will attempts to avoid creating images
            that match negative_prompt.
        simulate_nai: If True, will complete user-given (negative) prompts
            with additional (negative) prompt strings used by the nai
            model checkpoint.
        img2img_image_data: The input image in base64 encoding inluding the
            prefix ("data:image/png;base64").
        denoising_strength: The denoising factor.
        host: The machine that hosts the Stable Diffusion WebUI-API which
            will be used to have that machine create the images. If no
            host is specified, the default value from the config file will
            be used.

    Returns:
        A list of strings containing base64-encoded representations of the
        images, each prefixed with the substring "data:image/png;base64,".

    TODO:
        * Unify parameter handling/defaults (empty string vs. None vs.
            negative int)
    """

    # Seed fallback
    if seed == -1:
        seed = random.randint(0, 999999999)

    if host is None:
        host = config["GRADIO_API_BASE_URL"]

    print("interface img2img " + prompt + " /denoising strength: " +
          str(denoising_strength) + " /sampler: " + sampling_method_img2img)

    if simulate_nai:
        prompt = "masterpiece, best quality, " + prompt
        negative_prompt = ("lowres, bad anatomy, bad hands, text, error, " +
                           "missing fingers, extra digit, fewer digits, " +
                           "cropped, worst quality, low quality, " +
                           "normal quality, jpeg artifacts, signature, " +
                           "watermark, username, blurry, artist name, " +
                           negative_prompt)

    # Build the request for the HTTP API
    # TODO: saner defaults - from config?
    request = {
        "init_images": [
            img2img_image_data
        ],
        # "resize_mode": 0,
        "denoising_strength": denoising_strength,
        # "image_cfg_scale": 0,
        # "mask": "string",
        # "mask_blur": 4,
        # "inpainting_fill": 0,
        # "inpaint_full_res": true,
        # "inpaint_full_res_padding": 0,
        # "inpainting_mask_invert": 0,
        # "initial_noise_multiplier": 0,
        "prompt": prompt,
        # "styles": [
        #     "string"
        # ],
        "seed": seed,
        # "subseed": -1,
        # "subseed_strength": 0,
        # "seed_resize_from_h": -1,
        # "seed_resize_from_w": -1,
        "sampler_name": sampling_method_img2img,
        "batch_size": quantity,
        # "n_iter": 1,
        # "steps": 50,
        # "cfg_scale": 7,
        # "width": 512,
        # "height": 512,
        # "restore_faces": false,
        # "tiling": false,
        # "do_not_save_samples": false,
        # "do_not_save_grid": false,
        "negative_prompt": negative_prompt,
        # "eta": 0,
        # "s_churn": 0,
        # "s_tmax": 0,
        # "s_tmin": 0,
        # "s_noise": 1,
        # "override_settings": {},
        # "override_settings_restore_afterwards": true,
        # "script_args": [],
        # "sampler_index": "Euler",   # sampling_method_img2img ???
        #  "include_init_images": false,
        # "script_name": "string",
        # "send_images": true,
        # "save_images": false,
        # "alwayson_scripts": {}
    }

    images = []

    async with aiohttp.ClientSession() as session:
        async with (session.post(host + "/sdapi/v1/img2img", json=request) 
                    as response):
            response_json = await response.json()

            if debug_mode:
                with open(".debug.img2img_server_local_urls.json", "w",
                          encoding="utf-8") as f:
                    json.dump(response_json, f, ensure_ascii=False, indent=4)

            for img in response_json["images"]:
                images.append("data:image/png;base64," + img)

    """images =  [
        "data:image/png;base64,ABC...",
        "data:image/png;base64,ABC...",
        ...
    ]
    """
    return images
