import base64
import json
import aiohttp
import asyncio
from dotenv import dotenv_values
import random
from random import randint

config = dotenv_values('.env')
debug_mode=bool(config['DEBUG_MODE'] == "True")

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
                    return session
                    
    # Checks all components (=Buttons) in the webui for the one with the given label. 
    # If the label exists multiple times ("Save"-Button), give the occurrence. For example, "Find me the second save button on the webpage"
    def find_button_to_string(self, label, occurrence=1):
        current_occurrence = 0
        for component in self.gradioconfig["components"]:
            if component["props"].get("value") == label:
                current_occurrence += 1
                if current_occurrence == occurrence:
                    return component["id"]
        # We should not reach here. The component wasnt found? That means Gradio web ui changed AGAIN
        raise ValueError("Elrond: Could not find \"" + label + "\" number " + str(occurrence) + " in the web interface gradio config. Go into your browser and check if the button with this label is still there." )
        
    # Finds the default value on the webui for certain labels. For example if the user configured a default prompt. ("Masterpiece, best quality")
    def find_value_for_label(self, label, search_criteria = []):
        value = None
        for component in self.gradioconfig["components"]:
            if component["props"].get("label") == label:
                search_ok = True
                if len(search_criteria) > 0:
                    # Optionally, check if the label fits search criteria
                    for criteria in search_criteria:
                        # All properties must be present and euqal to the search value
                        if component["props"].get(criteria["property_name"]) != criteria["property_value"]:
                            search_ok = False
                            break
                if search_ok:
                    value = str(component["props"].get("value"))
                    break
        # If a value is defined, return it
        return value

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
                for default_values in self.gradioconfig["components"]:
                    if default_values["id"] == d_id:
                        default_value = default_values["props"].get("value")
                        # Gradio sometimes says the default value is "None", but if we send None for certain object types, it crashes
                        if default_value == None:
                            # Multiselects want an empty array instead of None
                            if default_values["props"].get("multiselect", False):
                                default_value = []
                            # Labels want to have a numeric zero as value
                            if default_values.get("type", "") == "label":
                                default_value = 0
                        data.append(default_value)
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
                for default_values in self.gradioconfig["components"]:
                    if default_values["id"] == d_id:
                        default_value = default_values["props"].get("value")
                        # Gradio sometimes says the default value is "None", but if we send None for certain object types, it crashes
                        if default_value == None:
                            # Multiselects want an empty array instead of None
                            if default_values["props"].get("multiselect", False):
                                default_value = []
                            # Labels want to have a numeric zero as value
                            if default_values.get("type", "") == "label":
                                default_value = 0
                        data.append(default_value)
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
