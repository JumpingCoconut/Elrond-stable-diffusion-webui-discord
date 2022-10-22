import base64
import json
import aiohttp
import asyncio
from dotenv import dotenv_values
import random
from random import randint

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


class GradioFunctionMapper:
    def __init__(self):
        # Ask the gradio webserver what gradio components there are on the webui, and what dependencies on other components they have
        self.gradioconfig = {}
        async with aiohttp.ClientSession() as session:
            async with session.get(["GRADIO_API_BASE_URL"] + "/config") as resp:
                if resp.status == 200:
                    r = await resp.json()
                    if debug_mode:
                        with open('.debug.gradio_config.json', 'w', encoding='utf-8') as f:
                            json.dump(r, f, ensure_ascii=False, indent=4)
                    self.gradioconfig = r
        # Storage for our own values, like seed and the like
        self.component_values = []
                    
    # Checks all components (=Buttons) in the webui for the one with the given label. 
    # If the label exists multiple times ("Save"-Button), give the occurrence. For example, "Find me the second save button on the webpage"
    def find_button_to_string(label, occurrence):
        current_occurrence = 0
        for component in self.gradioconfig["components"]:
            if component["props"].get("value") == label:
                current_occurrence += 1
                if current_occurrence == occurrence:
                    return component["id"]
        # We should not reach here. The component wasnt found? That means Gradio web ui changed AGAIN
        raise ValueError("Elrond: Could not find \"" + label + "\" number " + str(occurrence) + " in the web interface gradio config. Go into your browser and check if the button with this label is still there." )
        
    # Returns the function id and all component IDs that are needed to trigger the given component
    def find_dependency_data_to_component(component_id):
        dependency_data = {}
        fn_index = 0
        for dep in range(0, len(self.gradioconfig["dependencies"])):
            # The value "targets" tells us for which components this action is intended. We can stop as soon as we find our component here
            targets =  dependenciesjson[dep].get["targets"]
            if targets:
                if component_id in targets:
                    # We got our entry. Save all the dependencies
                    dependency_data = dependenciesjson[dep].copy()
                    # Also, the function index is just the array counter for the gradio dependencies list
                    fn_index = dep
                    break
        # We should not reach here. The component wasnt found? That means Gradio web ui changed AGAIN
        raise ValueError("Elrond: Could not find any dependencies for component " + str(component_id) + ". Check " + ["GRADIO_API_BASE_URL"] + "/config and see what component id this is and why we have no dependencies anymore. Dependencies are needed to trigger the web server.")

    # Updates all components that we have based on the label name. If something with this label name is to be used for sending data, we just take our data for it. No matter where it is
    def set_this_label_to_value(label, our_data):
        for component in self.gradioconfig["components"]:
            if component["props"].get("label") == label:
                self.component_values.update({"id":component["id"], "value":our_data})
        # We should not reach here. The component wasnt found? That means Gradio web ui changed AGAIN
        raise ValueError("Elrond: Could not find \"" + label + "\" in the web interface gradio config. Go into your browser and check if the label with this name is still there." )
        
    # Function is int, dependency data is an array with ints
    def build_request_with_components(fn_index, dependencies)
        # Check all given dependencies and fill them with their values
        dependency_data = []
        for d_id in dependencies:
            # Check if we have the value stored
            value_found = False
            for our_value in self.component_values:
                if our_value["id"] == d_id:
                    dependency_data.append(our_value["value"])
                    value_found = True
                    break
            # We dont have the value for this component yet, read the default value
            if not value_found:
                for default_value in self.gradioconfig["components"]:
                    if default_value["id"] == d_id:
                        dependency_data.append(default_value["props"].get("value"))
                        break
                        
        # Now build the string
        request = { 
                    "fn_index":fn_index,
                    "data": dependency_data,
                    "session_hash":"haschisch"
                  }
        return request
        
    # For the next request, hold our components of the last request to easily submit them
    def save_response_in_our_components(response, output_component_ids):
        # Check if the output has the expected size
        if len(response["data"]) != len(output_component_ids):
            raise ValueError("Elrond: The server reply was not as expected. We need the component ids " + str(output_component_ids) + ". We got " + str(response["data"]) + ". Check " + ["GRADIO_API_BASE_URL"] + "/config and check the part that says \"dependencies\".")
        # And now we can just copy it over
        for i in range(0, len(output_component_ids)):
            self.component_values.update({"id":output_component_ids[i], "value":response["data"][i]})
        
    def txt2img(prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = ""):
        # Search for the first Generate-Buttton, which is txt2img
        target = find_button_to_string("Generate", 1)
        # target = find_button_to_string("Save", 1) # First save button
        # target = find_button_to_string("Generate", 2) #Second would be img2img
        # target = find_button_to_string("Generate", 3) #Third generate button is the upscaler
        
        # Which function does this button execute?
        dependency_data = {}
        fn_index, dependency_data = find_dependency_data_to_component(target)
        
        # Now we search the webui for labels with these names, and just fill our values in.
        set_this_label_to_value("Prompt", prompt)
        set_this_label_to_value("Prompts", prompt) # There is one label called "Prompts" instead of "Prompt", but is it important?
        set_this_label_to_value("Seed", seed)
        set_this_label_to_value("Batch count", quantity)
        set_this_label_to_value("Negative prompt", negative_prompt)
        
        # Build a request string
        request = build_request_with_components(fn_index, dependency_data.get("inputs"))
        async with aiohttp.ClientSession() as session:
            async with session.post(config["GRADIO_API_BASE_URL"] + "/api/predict/", json=request) as resp:
                r = await resp.json()
                if  debug_mode:
                    with open('.debug.txt2img_server_local_urls.json', 'w', encoding='utf-8') as f:
                        json.dump(r, f, ensure_ascii=False, indent=4)
                # Save the response we got. We dont touch it we just forward it later.
                save_response_in_our_components(r, dependency_data.get("outputs"))
                
        # Now we call the save button function with just the same data. Copy paste from above with just a different button here
        target = find_button_to_string("Save", 1) # First save button
        fn_index, dependency_data = find_dependency_data_to_component(target)
        request = build_request_with_components(fn_index, dependency_data.get("inputs"))
        # Save the img urls
        img_urls = []
        async with aiohttp.ClientSession() as session:
            async with session.post(config["GRADIO_API_BASE_URL"] + "/api/predict/", json=request) as resp:
                r = await resp.json()
                if  debug_mode:
                    with open('.debug.txt2img_server_public_urls.json', 'w', encoding='utf-8') as f:
                        json.dump(r, f, ensure_ascii=False, indent=4)
                # And save the response again. But we can also use it 
                save_response_in_our_components(r, dependency_data.get("outputs"))
                for d in r["data"][0]["value"]:
                    img_urls.append(config["GRADIO_API_BASE_URL"] + "/file=" + d['name'].replace("\\", "/"))
                    
         # Now we have the public file URL. Download from there
        encoded_images = []
        for img_url in img_urls:
            image_data = download_image_from_url(img_url)
            encoded_images.append(image_data)

        return encoded_images
        # ToDO: If this works, do the upscaler, and img2img

