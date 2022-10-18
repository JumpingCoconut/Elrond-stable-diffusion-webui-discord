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
            "session_hash": "aaa"}
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:7860/api/predict/", json=data) as resp:
            r = await resp.json()
            return r['data'][0]
    #r = requests.post("http://localhost:7860/api/predict/", json=data)
    #return str(r.json()['data'][0])
    
    
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
            encoded_image,
            None,
            0,
            0,
            0,
            size,
            "Lanczos",
            "None",
            1, [], "", ""
        ],
        "session_hash": "abasbasb"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:7860/api/predict/", json=data) as resp:
            r = await resp.json()
            return r['data'][0][0]
    
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
    data = {"fn_index": 12,
            "data": [prompt,
                     negative_prompt,
                     "None",
                     "None",
                     28, #prompt.steps,
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
                     512, #prompt.width,
                     512, #prompt.height,
                     False,
                     False,
                     0.7,
                     "None", # Script, can be set to "Prompts from file or textbox"
                     False,
                     False,
                     None,# File, if Script is selected. Example: {'name': "file.txt", "size": len(prompt), "data": b64_prompt},
                     "",# Textbox, if Script is selected. 
                     "Seed",
                     "",
                     "Steps",
                     "",
                     True,
                     False,
                     None],
            "session_hash": "aaa"}

    encoded_images = ""
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:7860/api/predict/", json=data) as resp:
            r = await resp.json()
            if  debug_mode:
                with open('data.json', 'w', encoding='utf-8') as f:
                    json.dump(r, f, ensure_ascii=False, indent=4)
            encoded_images = r['data'][0]
    
    return encoded_images
