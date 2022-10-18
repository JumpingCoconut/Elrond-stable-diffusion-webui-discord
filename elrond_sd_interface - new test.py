import base64
import json
import aiohttp
import asyncio
from dotenv import dotenv_values
import random
from random import randint

config = dotenv_values('.env')
debug_mode=bool(config['DEBUG_MODE'])

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
        async with session.post("http://localhost:7860/api/predict/", json=data) as resp:
            r = await resp.json()
            return r['data'][0]    
    
# Download image from url, then interrogate
async def interface_interrogate_url(img_url, type):
    print("Downloading " + img_url)
    
    image_data = ""
    async with aiohttp.ClientSession() as session:
        async with session.get(img_url) as resp:
            if resp.status == 200:
                #f = await aiofiles.open('/some/file.img', mode='wb')
                #await f.write(await resp.read())
                #await f.close()
                file = await resp.read()
                image_data = "data:image/png;base64," + str(base64.b64encode(file).decode("utf-8"))
            
    if  image_data != "":
        return await interface_img_interrogate(image_data, type)
    else:
        return None
    

# Make image bigger
async def interface_upscale_image(encoded_image, size=2):
    data = {
        "fn_index": 42,
        "data": [
            0,
            0,
            encoded_image,
            None,
            "",
            "",
            True,
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
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:7860/api/predict/", json=data) as resp:
            r = await resp.json()
            with open(r['data'][0][0]['name'], "rb") as image_file:
                return str("data:image/png;base64," + base64.b64encode(image_file.read()).decode('utf-8'))
                
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
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:7860/api/predict/", json=data) as resp:
            r = await resp.json()
            if  debug_mode:
                with open('.debug.data.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            files = r['data'][0]
            # convert each file int b64
            encoded_images = []
            for file in files:
                with open(file['name'], "rb") as image_file:
                    encoded_images.append("data:image/png;base64," + base64.b64encode(image_file.read()).decode('utf-8'))
    return encoded_images

# ToDo: img2img, used to be fn_index 31. Old data:
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