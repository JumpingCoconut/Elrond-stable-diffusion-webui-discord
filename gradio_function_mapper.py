import base64
import json
import aiohttp
import asyncio
from dotenv import dotenv_values
import random
from random import randint

config = dotenv_values('.env')
debug_mode=bool(config['DEBUG_MODE'])

class GradioFunctionMapper:
    def __init__(self, integration_environment=False):
        # Test mode or real mode?
        if integration_environment:
            self.gradio_api_base_url = config["GRADIO_API_INTEGRATION_ENVIRONMENT"]
            self.debug_filename = ".debug.int."
        else:
            self.gradio_api_base_url = config["GRADIO_API_BASE_URL"] 
            self.debug_filename = ".debug.prod."
        # Storage for the webserver api definition by gradio
        self.gradioconfig = {}
        self.gradioconfig_version = ""
        # Storage for our own values, like seed and the like
        self.component_values = []
        
    async def setup(self):
        # Ask the gradio webserver what gradio components there are on the webui, and what dependencies on other components they have
        async with aiohttp.ClientSession() as session:
            async with session.get(self.gradio_api_base_url + "/config") as resp:
                if resp.status == 200:
                    r = await resp.json()
                    if debug_mode:
                        with open(self.debug_filename + 'gradio_config.json', 'w', encoding='utf-8') as f:
                            json.dump(r, f, ensure_ascii=False, indent=4)

                    self.gradioconfig = r
        self.gradioconfig_version = self.gradioconfig["version"]

                    
# Takes any URL and downloads the image from there, returns image data
    async def download_image_from_url(self, img_url):
        image_data = ""
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as resp:
                if resp.status == 200:
                    file = await resp.read()
                    image_data = "data:image/png;base64," + str(base64.b64encode(file).decode("utf-8"))
        return image_data
                    
    # Checks all components (=Buttons) in the webui for the one with the given label. 
    # If the label exists multiple times ("Save"-Button), give the occurrence. For example, "Find me the second save button on the webpage"
    def find_button_to_string(self, label, occurrence):
        current_occurrence = 0
        for component in self.gradioconfig["components"]:
            if component["props"].get("value") == label:
                current_occurrence += 1
                if current_occurrence == occurrence:
                    return component["id"]
        # We should not reach here. The component wasnt found? That means Gradio web ui changed AGAIN
        raise ValueError("Elrond: Could not find \"" + label + "\" number " + str(occurrence) + " in the web interface gradio config. Go into your browser and check if the button with this label is still there." )
        
    # Returns the function id and all component IDs that are needed to trigger the given component
    def find_dependency_data_to_component(self, component_id):
        dependency_data = {}
        fn_index = 0
        for dep in range(0, len(self.gradioconfig["dependencies"])):
            # The value "targets" tells us for which components this action is intended. We can stop as soon as we find our component here
            targets =  self.gradioconfig["dependencies"][dep].get("targets")
            if targets:
                if component_id in targets:
                    # We got our entry. Save all the dependencies
                    dependency_data = self.gradioconfig["dependencies"][dep].copy()
                    # Also, the function index is just the array counter for the gradio dependencies list
                    fn_index = dep
                    return fn_index, dependency_data
        # We should not reach here. The component wasnt found? That means Gradio web ui changed AGAIN
        raise ValueError("Elrond: Could not find any dependencies for component " + str(component_id) + ". Check " + self.gradio_api_base_url + "/config and see what component id this is and why we have no dependencies anymore. Dependencies are needed to trigger the web server.")

    # Saves a value to a component, for example sets the prompt to a prompt label
    def set_component_to_value(self, component_id, value):
        # First, check if we have the component already
        component_exists = False
        for i in range(0, len(self.component_values)):
            if self.component_values[i]["id"] == component_id:
                self.component_values[i]["value"] = value
                component_exists = True
                break
        # Add it to our component list
        if not component_exists:
            self.component_values.append({"id":component_id, "value":value})

    # Updates all components that we have based on the label name. If something with this label name is to be used for sending data, we just take our data for it. No matter where it is
    def set_this_label_to_value(self, label, our_data):
        label_exists = False
        for component in self.gradioconfig["components"]:
            if component["props"].get("label") == label:
                self.set_component_to_value(component["id"], our_data)
                label_exists = True
        # The component wasnt found? That means Gradio web ui changed AGAIN
        if not label_exists:
            raise ValueError("Elrond: Could not find \"" + label + "\" in the web interface gradio config. Go in the webui " +  self.gradio_api_base_url + " and check if the label with this name is still there." )
        
    # Searches for image fields and updates them. If given a search label or id, only updates those images.
    def search_imagefields_and_set_value(self, imagedata, search_criteria=[]):
        image_found = False
        for component in self.gradioconfig["components"]:
            if component["type"] == "image":
                update_ok = True
                if len(search_criteria) > 0:
                    # Optionally, check if the image fits search criteria
                    for criteria in search_criteria:
                        # All properties must be present and euqal to the search value
                        if component["props"].get(criteria["property_name"]) != criteria["property_value"]:
                            update_ok = False
                            break
                if update_ok:
                    self.set_component_to_value(component["id"], imagedata)
                    image_found = True
        # The image wasnt found? That means Gradio web ui changed AGAIN
        if not image_found:
            raise ValueError("Elrond: Could not find an option to upload an image in the gradio web interface. Check " + self.gradio_api_base_url + "/config and see if there are still images defined with type \"image\". Searched image: " + str(search_criteria))
        
    # Function is int, dependency data is an array with ints
    def build_request_with_components(self, fn_index, input_dependencies, output_dependencies):
        # Check all given dependencies and fill them with their values
        data = []
        for d_id in input_dependencies:
            # Check if we have the value stored
            value_found = False
            for our_value in self.component_values:
                if our_value["id"] == d_id:
                    data.append(our_value["value"])
                    value_found = True
                    break
            # We dont have the value for this component yet, read the default value
            if not value_found:
                for default_value in self.gradioconfig["components"]:
                    if default_value["id"] == d_id:
                        data.append(default_value["props"].get("value"))
                        break
        # The request also expects all output dependencies. Give them with default values
        for d_id in output_dependencies:
            # Check if we have the value stored
            #value_found = False
            #for our_value in self.component_values:
                #if our_value["id"] == d_id:
                    #data.append(our_value["value"])
                    #value_found = True
                    #break
            # We dont have the value for this component yet, read the default value
            if not value_found:
                for default_value in self.gradioconfig["components"]:
                    if default_value["id"] == d_id:
                        data.append(default_value["props"].get("value"))
                        break

        # Now build the string
        request = { 
                    "fn_index":fn_index,
                    "data": data,
                    "session_hash":"haschisch"
                  }
        return request
        
    # For the next request, hold our components of the last request to easily submit them
    def save_response_in_our_components(self, response, output_component_ids):
        # Check if the output has the expected size
        if len(response["data"]) != len(output_component_ids):
            raise ValueError("Elrond: The server reply was not as expected. We need the component ids " + str(output_component_ids) + ". We got " + str(response["data"]) + ". Check " + self.gradio_api_base_url + "/config and check the part that says \"dependencies\".")
        # And now we can just copy it over
        for i in range(0, len(output_component_ids)):
            self.set_component_to_value(output_component_ids[i], response["data"][i])
        
    async def txt2img(self, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = ""):
        # Search for the first Generate-Buttton, which is txt2img
        target = self.find_button_to_string("Generate", 1)
        # target = self.find_button_to_string("Save", 1) # First save button
        # target = self.find_button_to_string("Generate", 2) #Second would be img2img
        # target = self.find_button_to_string("Generate", 3) #Third generate button is the upscaler
        
        # Which function does this button execute?
        dependency_data = {}
        fn_index, dependency_data = self.find_dependency_data_to_component(target)
        
        # Now we search the webui for labels with these names, and just fill our values in.
        self.set_this_label_to_value("Prompt", prompt)
        self.set_this_label_to_value("Prompts", prompt) # There is one label called "Prompts" instead of "Prompt", but is it important?
        self.set_this_label_to_value("Seed", seed)
        self.set_this_label_to_value("Batch count", quantity)
        self.set_this_label_to_value("Negative prompt", negative_prompt)
        
        # Build a request string
        request = self.build_request_with_components(fn_index, dependency_data.get("inputs"), dependency_data.get("outputs"))
        async with aiohttp.ClientSession() as session:
            async with session.post(self.gradio_api_base_url + "/api/predict/", json=request) as resp:
                r = await resp.json()
                if  debug_mode:
                    with open(self.debug_filename + 'txt2img_server_local_urls.json', 'w', encoding='utf-8') as f:
                        json.dump(r, f, ensure_ascii=False, indent=4)
                # In Gradio 3.4b, we now get all the images and are already done. In other versions we must do more
                if self.gradioconfig_version == "3.4b3\n":
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
                # - The third element must be "-1" numeric
                for i in range(0, len(r["data"][0])):
                    local_filename = r["data"][0][i]["name"]
                    r["data"][0][i]["data"] = "file=" + local_filename
                    r["data"][0][i]["is_file"] = True
                r["data"][2] = int(-1)
                # Also, it returned some huge prompt text. We dont need that, messes up future requests, remove it

                # Save the response we got. We dont touch it we just forward it later.
                self.save_response_in_our_components(r, dependency_data.get("outputs"))
                
        # Now we call the save button function with just the same data. Copy paste from above with just a different button here
        target = self.find_button_to_string("Save", 1) # First save button
        fn_index, dependency_data = self.find_dependency_data_to_component(target)
        request = self.build_request_with_components(fn_index, dependency_data.get("inputs"), dependency_data.get("outputs"))
        # Save the img urls
        img_urls = []
        async with aiohttp.ClientSession() as session:
            async with session.post(self.gradio_api_base_url + "/api/predict/", json=request) as resp:
                r = await resp.json()
                if  debug_mode:
                    with open(self.debug_filename + 'txt2img_server_public_urls.json', 'w', encoding='utf-8') as f:
                        json.dump(r, f, ensure_ascii=False, indent=4)
                # And save the response again. But we can also use it 
                self.save_response_in_our_components(r, dependency_data.get("outputs"))
                for d in r["data"][0]["value"]:
                    img_urls.append(self.gradio_api_base_url + "/file=" + d['name'].replace("\\", "/"))
                    
         # Now we have the public file URL. Download from there
        encoded_images = []
        for img_url in img_urls:
            image_data = await self.download_image_from_url(img_url)
            encoded_images.append(image_data)

        return encoded_images
        # ToDO: If this works, do the upscaler, and img2img

