import base64
import json
import aiohttp
import asyncio
from dotenv import dotenv_values
import random
from random import randint
from gradio_function_mapper import GradioFunctionMapper

config = dotenv_values('.env')
debug_mode=bool(config['DEBUG_MODE'])

# Takes any URL and downloads the image from there, returns image data
async def download_image_from_url(img_url):
    image_data = ""
    async with aiohttp.ClientSession() as session:
        async with session.get(img_url) as resp:
            if resp.status == 200:
                #f = await aiofiles.open('/some/file.img', mode='wb')
                #await f.write(await resp.read())
                #await f.close()
                file = await resp.read()
                image_data = "data:image/png;base64," + str(base64.b64encode(file).decode("utf-8"))
    return image_data

# Check image, generate text
async def interface_img_interrogate(image_data, type):
    # Todo: Check if this changed
    fn_index_interrogate = 0
    if  type == "tags":
        fn_index_interrogate = 33
    elif type == "desc":
        fn_index_interrogate = 32
    else:
        return None
    print("interrogating image for " + type)
    data = {"fn_index": fn_index_interrogate,
            "data": [image_data],
            "session_hash": "haschisch"}
    async with aiohttp.ClientSession() as session:
        async with session.post(config["GRADIO_API_BASE_URL"] + "/api/predict/", json=data) as resp:
            r = await resp.json()
            return r['data'][0]    
    
# Download image from url, then interrogate
async def interface_interrogate_url(img_url, type):
    print("Downloading " + img_url)
    image_data = download_image_from_url(img_url)
    if  image_data != "":
        return await interface_img_interrogate(image_data, type)
    else:
        return None
    

# Make image bigger
async def interface_upscale_image(encoded_image, size=2):
    data = {
        "fn_index": 43,
        "data": [
            0,
            0,
            encoded_image,
            None,
            0,
            0,
            0,
            size,
            512,
            512,
            True,
            "Lanczos",
            "None",
            1, [], "", ""
        ],
        "session_hash": "haschisch"
    }
    img_url = ""
    async with aiohttp.ClientSession() as session:
        async with session.post(config["GRADIO_API_BASE_URL"] + "/api/predict/", json=data) as resp:
            r = await resp.json()
            if  debug_mode:
                with open('.debug.upscale_image.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            img_url = config["GRADIO_API_BASE_URL"] + "/file=" + r['data'][0][0]['name'].replace("\\", "/")
    # Now we have the file URL. Download from there
    image_data = download_image_from_url(img_url)
    return image_data
                
# Text prompt to image
async def interface_txt2img(prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = "", simulate_nai: bool = True):
 
    # Seed fallback
    if seed == -1:
        seed = random.randint(0, 999999999)
        
    print("Generating txt2img for " + prompt)
    
    # Wir machen genau wie NAI immer zwei extra Tags
    if  simulate_nai:
        prompt = "masterpiece, best quality, " + prompt
        negative_prompt = " lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, artist name, " + negative_prompt
    
    # Fuck it try the new thing
    gradio_mapper = GradioFunctionMapper(prompt, seed, quantity, negative_prompt)
    return gradio_mapper.txt2img()
    
    
    
    #b64_prompt = base64.b64encode(prompt.encode()).decode('utf-8')
    #b64_prompt = "data:text/plain;base64," + b64_prompt
    data = {"fn_index": 13,
            "data": [prompt,
                     negative_prompt,
                     "None",
                     "None",
                     28, # steps,
                     config['SAMPLER'],
                     False,
                     False,
                     quantity,
                     int(config['BATCH_SIZE']),
                     int(config["CFG_SCALE"]),
                     seed,
                     -1,
                     0,
                     0,
                     0,
                     False,
                     512, # width,
                     512, # height,
                     False,
                     0.7,
                     0,
                     0,
                     "None", # Script, can be set to "Prompts from file or textbox"
                     False,
                     False,
                     None,# File, if Script is selected. Example: {'name': "file.txt", "size": len(prompt), "data": b64_prompt},
                     "",# Textbox, if Script is selected. 
                     "Seed",
                     "",
                     "Nothing",
                     "",
                     True,
                     False,
                     False,
                     None,
                     None,
                     None],
            "session_hash": "haschisch"}
    encoded_images = []
    server_local_filename = []
    async with aiohttp.ClientSession() as session:
        async with session.post(config["GRADIO_API_BASE_URL"] + "/api/predict/", json=data) as resp:
            r = await resp.json()
            if  debug_mode:
                with open('.debug.txt2img_server_local_urls.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            # Now we have the images. But only as local file paths on the server! Oh no
            for d in r["data"][0]:
                server_local_filename.append(d['name'])
                    
    # Now the image is generated. Tell the API to save them in an accessible path for us
    all_prompts = []
    all_seeds = []
    infotexts = []
    for n in range(quantity):
        all_prompts.append(prompt)
        all_seeds.append(seed + n)
        # No idea what Model hash is, but this is the textbox that is printed underneath the save button so maybe its important
        infotexts.append(prompt + "\n" + str({"Steps" : 28, "Sampler" : "Euler a", "CFG scale" : 7, "Seed" : (seed+n), "Size" : "512x512", "Model hash" : "keinAhnung", "Clip skip" : 2}).replace("{","").replace("}", "").replace("'", ""))
    data = {"fn_index":16,
            "data": [
                      #"{\"prompt\": \"cute\", \"all_prompts\": [\"cute\", \"cute\"], \"negative_prompt\": \"\", \"seed\": 3765296599, \"all_seeds\": [3765296599, 3765296600], \"subseed\": 3082624139, \"all_subseeds\": [3082624139, 3082624140], \"subseed_strength\": 0, \"width\": 512, \"height\": 512, \"sampler_index\": 0, \"sampler\": \"Euler a\", \"cfg_scale\": 7, \"steps\": 20, \"batch_size\": 1, \"restore_faces\": false, \"face_restoration_model\": null, \"sd_model_hash\": \"925997e9\", \"seed_resize_from_w\": 0, \"seed_resize_from_h\": 0, \"denoising_strength\": null, \"extra_generation_params\": {}, \"index_of_first_image\": 1, \"infotexts\": [\"cute\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 3765296599, Size: 512x512, Model hash: 925997e9, Clip skip: 2\", \"cute\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 3765296599, Size: 512x512, Model hash: 925997e9, Clip skip: 2\", \"cute\\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 3765296600, Size: 512x512, Model hash: 925997e9, Clip skip: 2\"], \"styles\": [\"None\", \"None\"], \"job_timestamp\": \"20221019194839\", \"clip_skip\": 2}",
                      # Some are missing but maybe these are enough. Infotexts has a lot of info texts. If this doesnt work then the rest of the string can be hard-coded except of "subseeds", but no idea what that is.
                      {"prompt" : prompt, "all_prompts" : all_prompts, "negative_prompt" : negative_prompt, "seed" : seed, "all_seeds" : all_seeds, "index_of_first_image" : 1, "infotexts" : infotexts},
                      #"{\"batch_count\": " + str(quantity) + "}",
                      #"",
                      [

                      ],
                      False,
                      -1
                    ],
            "session_hash":"haschisch"
            }
    # API needs the path on the local server to convert it into a public url
    for filen in server_local_filename:
        data["data"][1].append({
                            "name":filen,#"C:\\Users\\abc\\AppData\\Local\\Temp\\tmp38r80fot\\tmpnewrq176.png",
                            "data":"file=" + filen,#C:\\Users\\abc\\AppData\\Local\\Temp\\tmp38r80fot\\tmpnewrq176.png",
                            "is_file":True
                         })
    # Convert local server paths to public URLs
    img_urls = []
    async with aiohttp.ClientSession() as session:
        async with session.post(config["GRADIO_API_BASE_URL"] + "/api/predict/", json=data) as resp:
            r = await resp.json()
            if  debug_mode:
                with open('.debug.txt2img_server_public_urls.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            for d in r["data"][0]["value"]:
                img_urls.append(config["GRADIO_API_BASE_URL"] + "/file=" + d['name'].replace("\\", "/"))
            
    # Now we have the public file URL. Download from there
    for img_url in img_urls:
        image_data = download_image_from_url(img_url)
        encoded_images.append(image_data)

    return encoded_images

# ToDo: img2img, used to be fn_index 31. Old data record:
  # data = {"fn_index": 31,
            # "data": [0,
                     # prompt_list_text,
                     # prompt_list_negative_text,
                     # "None",
                     # "None",
                     # image_data.data,
                     # None,
                     # None,
                     # None,
                     # "Draw mask",
                     # prompt.steps,
                     # "Euler a",
                     # 4,
                     # "original",
                     # False,
                     # False,
                     # quantity,
                     # int(config['BATCH_SIZE']),
                     # int(config["CFG_SCALE"]),
                     # 0.6, # Denoising strength 0.75
                     # prompt.seed,
                     # -1,
                     # 0,
                     # 0,
                     # 0,
                     # False,
                     # prompt.width,
                     # prompt.height,
                     # "Just resize",
                     # False,
                     # 32,
                     # "Inpaint masked",
                     # "",
                     # "",
                     # "None",
                     # "",
                     # "",
                     # 1,
                     # 50,
                     # 0,
                     # False,
                     # 4,
                     # 1,
                     # "<p style=\"margin-bottom:0.75em\">Recommended settings: Sampling Steps: 80-100, Sampler: Euler a, Denoising strength: 0.8</p>",
                     # 128,
                     # 8,
                     # [
                        # "left",
                        # "right",
                        # "up",
                        # "down"
                     # ],
                     # 1,
                     # 0.05,
                     # 128,
                     # 4,
                     # "fill",
                     # [
                        # "left",
                        # "right",
                        # "up",
                        # "down"
                     # ],
                     # False,
                     # False,
                     # None,
                     # "",
                     # "<p style=\"margin-bottom:0.75em\">Will upscale the image to twice the dimensions; use width and height sliders to set tile size</p>",
                     # 64,
                     # "None",
                     # "Seed",
                     # "",
                     # "Steps",
                     # "",
                     # True,
                     # False,
                     # None,
                     # False,
                     # None],
            # "session_hash": "haschisch"}