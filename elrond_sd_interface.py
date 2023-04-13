import asyncio
import base64
import json
import random
from random import randint

import aiohttp
from dotenv import dotenv_values

from gradio_function_mapper import GradioFunctionMapper

config = dotenv_values('.env')
debug_mode = bool(config['DEBUG_MODE'] == "True")
use_webui_default_prompts = bool(config['USE_WEBUI_DEFAULT_PROMPTS'] == "True")
sampling_method_txt2img = str(config['SAMPLING_METHOD_TXT2IMG'])
sampling_method_img2img = str(config['SAMPLING_METHOD_IMG2IMG'])

# Takes any URL and downloads the image from there, returns image data


async def download_image_from_url(img_url):
    image_data = ""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(img_url) as resp:
                if resp.status == 200:
                    # f = await aiofiles.open('/some/file.img', mode='wb')
                    # await f.write(await resp.read())
                    # await f.close()
                    file = await resp.read()
                    image_data = "data:image/png;base64," + \
                        str(base64.b64encode(file).decode("utf-8"))
        except Exception as e:
            print("Download of " + img_url + " failed: " + str(e))
    return image_data

# Check image, generate text


async def interface_img_interrogate(image_data, type):
    print("Interrogate type " + str(type))
    # To do requests to the gradio webserver which is used by stable diffusion webui, we need to get the request formats first
    # We are in Test mode
    gradio_mapper = GradioFunctionMapper(integration_environment=False)
    await gradio_mapper.setup()

    # Search for the Interrogate button on the webui by label
    buttonname = ""
    if type == "tags":
        buttonname = "Interrogate\nDeepBooru"
    elif type == "desc":
        buttonname = "Interrogate\nCLIP"
    else:
        return None
    target = gradio_mapper.find_button_to_string(buttonname, 1)

    # Which function does this button execute? And which components are needed to start this function?
    dependency_data = {}
    fn_index, dependency_data = gradio_mapper.find_dependency_data_to_component(
        target)

    # Search for the image in the img2img tab, where the interrogate button resides.
    # The correct image field on the website has the elem_id "img2img_image"
    image_searchcriteria = [
        {"property_name": "elem_id", "property_value": "img2img_image"},
        {"property_name": "source", "property_value": "upload"}
    ]
    # And paste our image data into this image on the webui
    gradio_mapper.search_imagefields_and_set_value(
        image_data, image_searchcriteria)

    # Build the request string. The previously set values will be inserted at the correct position automatically.
    request = gradio_mapper.build_request_with_components(
        fn_index, dependency_data.get("inputs"), dependency_data.get("outputs"))
    image_description = None
    async with aiohttp.ClientSession() as session:
        async with session.post(gradio_mapper.gradio_api_base_url + "/api/predict/", json=request) as resp:
            r = await resp.json()
            if debug_mode:
                with open(gradio_mapper.debug_filename + 'interrogate_image.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            # Regardless of Gradio version, the interrogate result is always in the first index of return data
            # If this ever changes, ask the version like this: gradio_mapper.gradioconfig_version == "3.5\n":
            image_description = r['data'][0]
    return image_description

# Download image from url, then interrogate


async def interface_interrogate_url(img_url, type):
    print("Downloading " + img_url)
    image_data = await download_image_from_url(img_url)
    if image_data != "":
        return await interface_img_interrogate(image_data, type)
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
                with (open('.debug.upscale_image.json', 'w', encoding='utf-8')
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
                with open('.debug.txt2img_server_local_urls.json', 'w',
                          encoding='utf-8') as f:
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

# Image to image


async def interface_img2img(prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = "", simulate_nai: bool = True, img2img_image_data: str = "", denoising_strength: float = 0.6, host: str = None):

    # Seed fallback
    if seed == -1:
        seed = random.randint(0, 999999999)

    print("interface img2img " + prompt + " /denoising strength: " +
          str(denoising_strength) + " /sampler: " + sampling_method_img2img)

    # To do requests to the gradio webserver which is used by stable diffusion webui, we need to get the request formats first
    gradio_mapper = GradioFunctionMapper(integration_environment=False)
    await gradio_mapper.setup()

    # Take the prompt and negative prompt default values from the webui
    if use_webui_default_prompts:
        default_prompt = gradio_mapper.find_value_for_label("Prompt")
        default_negative_prompt = gradio_mapper.find_value_for_label(
            "Negative prompt")
        if default_prompt:
            prompt = default_prompt + prompt
        if default_negative_prompt:
            # Negative prompt is optional so only modify it with a comma if user demands it
            if negative_prompt != "":
                negative_prompt = default_negative_prompt + ", " + negative_prompt
            else:
                negative_prompt = default_negative_prompt
    else:
        # NAI mode?
        if simulate_nai:
            prompt = "masterpiece, best quality, " + prompt
            negative_prompt = " lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, artist name, " + negative_prompt

    # Search for the second Generate-Button on the website, which is img2img
    target = gradio_mapper.find_button_to_string("Generate", 2)

    # Which function does this button execute? And which components are needed to start this function? (Should be txt2img)
    dependency_data = {}
    fn_index, dependency_data = gradio_mapper.find_dependency_data_to_component(
        component_id=target, js_string="submit_img2img")

    # Now we search the webui for labels with these names, and just fill our values in.
    gradio_mapper.set_this_label_to_value("Prompt", prompt)
    # gradio_mapper.set_this_label_to_value("Prompts", prompt) # There is one label called "Prompts" instead of "Prompt", but is it important? Update: Now called "List of prompt inputs"
    gradio_mapper.set_this_label_to_value("Seed", seed)
    gradio_mapper.set_this_label_to_value("Batch count", quantity)
    gradio_mapper.set_this_label_to_value("Negative prompt", negative_prompt)
    gradio_mapper.set_this_label_to_value(
        "Denoising strength", denoising_strength)
    if "|" in prompt:
        gradio_mapper.set_this_label_to_value("Script", "Prompt matrix")

    # Whats the default sampling method?
    label_searchcriteria = [
        {"property_name": "elem_id", "property_value": "img2img_sampling"},
    ]
    default_sampling_method = gradio_mapper.find_value_for_label(
        "Sampling method", label_searchcriteria)
    if default_sampling_method != sampling_method_img2img:
        print("Default sampling method would have been " + default_sampling_method)
    if sampling_method_img2img:
        gradio_mapper.set_this_label_to_value(
            "Sampling method", sampling_method_img2img)

    # Search for the image in the img2img tab
    # The correct image field on the website has the elem_id "img2img_image"
    image_searchcriteria = [
        {"property_name": "elem_id", "property_value": "img2img_image"},
        {"property_name": "source", "property_value": "upload"}
    ]
    # And paste our image data into this image on the webui
    gradio_mapper.search_imagefields_and_set_value(
        img2img_image_data, image_searchcriteria)

    # Build a request string. This has to include the function index, all needed input components and empty placeholders for output components.
    # The input components get filled automatically by the wrapper, based on our previous set labels.
    request = gradio_mapper.build_request_with_components(
        fn_index, dependency_data.get("inputs"), dependency_data.get("outputs"))
    async with aiohttp.ClientSession() as session:
        async with session.post(gradio_mapper.gradio_api_base_url + "/api/predict/", json=request) as resp:
            r = await resp.json()
            if debug_mode:
                with open(gradio_mapper.debug_filename + 'img2img_server_local_urls.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            # In Gradio 3.4b, we now get all the images and are already done. In other versions we must do more
            if gradio_mapper.gradioconfig_version == "3.4b3\n":
                encoded_images = r['data'][0]
                return encoded_images
            # In Gradio 3.5 upwards, we didnt get any images. We only get local paths that are only valid on the server. Example:
            """
{
"data": [
        [   {
                "name": "C:\\Users\\Elrond\\AppData\\Local\\Temp\\tmpmpa0a7_m\\tmphmyiw80h.png",
                "data": null,
                "is_file": true
            }, {
                "name": "C:\\Users\\Elrond\\AppData\\Local\\Temp\\tmpmpa0a7_m\\tmpk2_1rgez.png",
                "data": null,
                "is_file": true
            }, {
                "name": "C:\\Users\\Elrond\\AppData\\Local\\Temp\\tmpmpa0a7_m\\tmp534dswwy.png",
                "data": null,
                "is_file": true
            }, {
                "name": "C:\\Users\\Elrond\\AppData\\Local\\Temp\\tmpmpa0a7_m\\tmpklrac3bu.png",
                "data": null,
                "is_file": true
            }
        ], 
        "{\"prompt\": \"Multiple Horses\", \"all_prompts\": [\"Multiple Horses\", \"Multiple Horses\", \"Multiple Horses\"], \"negative_prompt\": \"\", \"seed\": 443715054, \"all_seeds\": [443715054, 443715055, 443715056], \"subseed\": 680975507, \"all_subseeds\": [680975507, 680975508, 680975509], \"subseed_strength\": 0, \"width\": 512, \"height\": 512, \"sampler_index\": 0, \"sampler\": \"Euler a\", \"cfg_scale\": 7, \"steps\": 20, \"batch_size\": 3, \"restore_faces\": false, \"face_restoration_model\": null, \"sd_model_hash\": \"925997e9\", \"seed_resize_from_w\": 0, \"seed_resize_from_h\": 0, \"denoising_strength\": null, \"extra_generation_params\": {}, \"index_of_first_image\": 1, \"infotexts\": [\"Multiple Horses\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 443715054, Size: 512x512, Model hash: 925997e9, Batch size: 3, Batch pos: 0\", \"Multiple Horses\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 443715054, Size: 512x512, Model hash: 925997e9, Batch size: 3, Batch pos: 0\", \"Multiple Horses\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 443715055, Size: 512x512, Model hash: 925997e9, Batch size: 3, Batch pos: 1\", \"Multiple Horses\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 443715056, Size: 512x512, Model hash: 925997e9, Batch size: 3, Batch pos: 2\"], \"styles\": [\"None\", \"None\"], \"job_timestamp\": \"20221021232038\", \"clip_skip\": 1}", 
        "<p>Multiple Horses<br>\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 443715054, Size: 512x512, Model hash: 925997e9, Batch size: 3, Batch pos: 0</p><div class='performance'><p class='time'>Time taken: <wbr>5.20s</p><p class='vram'>Torch active/reserved: 5317/6880 MiB, <wbr>Sys VRAM: 12288/12288 MiB (100.0%)</p></div>"],
"is_generating": false,
"duration": 5.202727794647217,
"average_duration": 20.910504698753357
            """
            # Edit the response now.
            # - The first element is missing "data" in all subelements. Fill it in a loop
            # - The second element is fine
            # - The third element is some huge text, but we need it to be "-1" numeric for our next request
            for i in range(0, len(r["data"][0])):
                local_filename = r["data"][0][i]["name"]
                r["data"][0][i]["data"] = "file=" + local_filename
                r["data"][0][i]["is_file"] = True
            r["data"][2] = int(-1)

            # Save the response we got. We dont touch it anymore, we just forward it later.
            gradio_mapper.save_response_in_our_components(
                r, dependency_data.get("outputs"))

    # Now we call the save button function with the previously saved data. Copy paste from above with just a different button here
    target = gradio_mapper.find_button_to_string(
        "Save", 2)  # Second save button
    fn_index, dependency_data = gradio_mapper.find_dependency_data_to_component(
        target)
    request = gradio_mapper.build_request_with_components(
        fn_index, dependency_data.get("inputs"), dependency_data.get("outputs"))
    # The save button will return us a bunch of direct img urls
    img_urls = []
    async with aiohttp.ClientSession() as session:
        async with session.post(gradio_mapper.gradio_api_base_url + "/api/predict/", json=request) as resp:
            r = await resp.json()
            if debug_mode:
                with open(gradio_mapper.debug_filename + 'img2img_server_public_urls.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            # And save the response again. But we probably wont use it
            gradio_mapper.save_response_in_our_components(
                r, dependency_data.get("outputs"))
            # The response has the image urls in the first data array field, "value":
            """"
{
    "data": [
        {
            "visible": true,
            "value": [
                {
                    "orig_name": "00039-3785918674-masterpiece, best quality, 1.png",
                    "name": "C:\\Users\\Elrond\\AppData\\Local\\Temp\\tmpf5juylk4\\00039-3785918674-masterpiece, best quality, 1l2vser04.png",
                    "size": 293071,
                    "data": null,
                    "is_file": true
                }
            ],
            "__type__": "update"
        },
        "",
        "",
        "<p>Saved: 00039-3785918674-masterpiece, best quality, 1.png</p><div class='performance'><p class='time'>Time taken: <wbr>0.10s</p><p class='vram'>Torch active/reserved: 2070/2084 MiB, <wbr>Sys VRAM: 4528/12288 MiB (36.85%)</p></div>"
    ],
    "is_generating": false,
    "duration": 0.10009098052978516,
    "average_duration": 0.09558689594268799
}           
            """
            # Do some formatting like replacing backslashes to get the well-formed url
            for d in r["data"][0]["value"]:
                img_urls.append(gradio_mapper.gradio_api_base_url +
                                "/file=" + d['name'].replace("\\", "/"))

    # Now we have the public file URL. Download from there
    encoded_images = []
    for img_url in img_urls:
        # Note: The return now can also contain a zip file with all images. Ignore that.
        if img_url.endswith(".png"):
            image_data = await download_image_from_url(img_url)
            encoded_images.append(image_data)

    return encoded_images
