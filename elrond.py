import base64
import asyncio
import json
import io
import random
import time
from random import randint
import requests
from dotenv import dotenv_values
import interactions
from interactions import Button, SelectMenu, SelectOption, spread_to_rows, autodefer
import aiohttp
from  elrond_sd_interface import *

# load env variables
config = dotenv_values('.env')

bot = interactions.Client(
    token=config['DISCORD_TOKEN']
)

# To use files in CommandContext send, you need to load it as an extension.
bot.load("interactions.ext.files")
# We load the Extension.
#bot.load("exts._files")


# Create a string like this: /draw prompt:Elrond sitting seed:123456789 quantity:2 negative_prompt:chair, bed
def create_command_string(prompt, seed, quantity, negative_prompt):
    command_string = "/draw prompt:" + prompt + " seed:" + str(seed) + " quantity:" + str(quantity)
    if negative_prompt:
        command_string = command_string + " negative_prompt:" + negative_prompt
    return command_string
    
# Parse a string like this: /draw prompt:Elrond sitting seed:123456789 quantity:2 negative_prompt:chair, bed
def parse_command_string(command_string):
    prompt = ""
    seed = "-1"
    quantity = "1"
    negative_prompt = ""
    
    pos = command_string.find('negative_prompt:')
    if pos > 0:
        negative_prompt = command_string[pos+16:]
        command_string = command_string[0:pos-1]
    
    pos = command_string.find('quantity:')
    if pos > 0:
        quantity = command_string[pos+9:]
        command_string = command_string[0:pos-1]
    
    pos = command_string.find('seed:')
    if pos > 0:
        seed = command_string[pos+5:]
        command_string = command_string[0:pos-1]
    
    pos = command_string.find('prompt:')
    if pos > 0:
        prompt = command_string[pos+7:]
    
    return prompt, int(seed), int(quantity), negative_prompt

async def draw_image(ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = "", message_notes: str = ""): #, apply_caption: bool = False):
    
    # So we dont get kicked
    botmessage = await ctx.send(f"Drawing {quantity} pictures of '{prompt}'!")
    
    # We need to know the seed for later use
    if seed == -1:
        seed = random.randint(0, 999999999)
        
    # Get data via web request
    encoded_images = await interface_txt2img(prompt, seed, quantity, negative_prompt)
    
    # If its multiple images, then the first one sent will be a grid of all other images combined
    if len(encoded_images) > 1:
        # User requested 4 or more images, ONLY send the comprehensive preview grid so the message doesnt bloat up
        if quantity >= 4:
            encoded_images = [encoded_images[0]]
        else:
            # Otherwise, skip the preview grid (first entry of this list)
            encoded_images.pop(0)
  
    # Make all images bigger and prepare them for discord
    uploaded_files = []
    used_seeds = []
    for i, encoded_image in enumerate(encoded_images):
        # Make the images bigger
        await botmessage.edit(f"Upscaling image {i+1} of {len(encoded_images)} for '{prompt}'...")
        upscaled_image = await interface_upscale_image(encoded_image) # a base64 encoded string starting with "data:image/png;base64," prefix

        # a base64 encoded string starting with "data:image/png;base64," prefix
        # remove the prefix
        z = upscaled_image[upscaled_image.find(',') + 1:]
        
        # The seed given is just the starting seed for the first image, all other images have ongoing numbers
        current_seed = seed + i
        used_seeds.append(current_seed)
        
        # Filename for upload
        filename = str(current_seed) + prompt[0:30] + ".png"
        
        # debug write
        #with open(filename, "wb") as fh:
            #fh.write(base64.b64decode(z))
        
        # Convert it into a discord file for later uploading them in bulk
        fxy = interactions.File(
            filename=filename,  
            fp=base64.b64decode(z)
            )
        uploaded_files.append(fxy)

    # ToDo: Upload them all as a temporary post on another discord, and then use embeds to pretty print them in the requester discord
    #await botmessage.edit(f"Uploading images to discord...")
    #tempmessage = await ctx.send(
        #content="Image for seed " + ",".join(map(str,used_seeds)),
        #files=uploaded_files
        #)
    
    # Prepare embeds for the pictures to make it prettier
    embeds = []
    for attachment in ctx.message.attachments: #tempmessage.attachments:
        
        # Paint the UI pretty
        embed = interactions.Embed(
                title=attachment.filename,
                description=prompt + "\n" + negative_prompt,
                #timestamp=datetime.datetime.now()
                color=interactions.Color.green(),
                footer=interactions.EmbedFooter(text=str(current_seed)),
                image=interactions.EmbedImageStruct(url=attachment.url),#"attachments://" + filename),
                provider=interactions.EmbedProvider(name="stable-diffusion-1-4, waifu-diffusion-1-3, nai, other"),
                author=interactions.EmbedAuthor(name=ctx.user.username + "#" + ctx.user.discriminator),
                #fields=[
                        #interactions.EmbedField(name="prompt",value=prompt,inline=True),
                        #interactions.EmbedField(name="seed",value=str(current_seed),inline=True),
                        #interactions.EmbedField(name="negative prompt",value=negative_prompt,inline=True),
                        #],
                )
        # Set negative prompt as footer
        if negative_prompt != "":
            embed.set_footer("Negative prompt: " + negative_prompt)
                
        embeds.append(embed)
        print(" ebmed added")
            
    # User inputs?
    b1 = Button(style=1, custom_id="same_prompt_again", label="Try again!")
    b2 = Button(style=3, custom_id="change_prompt", label="Keep seed, modify prompt")
    #s1 = SelectMenu(
        #custom_id="s1",
        #options=[
            #SelectOption(label="Ping ChaosEngel", value="1"),
            #SelectOption(label="Ping ChaosEngel three times in a row", value="2"),
        #],
    #)    
    #components = spread_to_rows(b1, b2)#, s1, b3, b4)
    components = [b1, b2]#, s1, b3, b4)
    
    # Give out the complete message with the command that can be used to replicate it
    content = create_command_string(prompt, seed, quantity, negative_prompt)
    if message_notes != "":
        content = content + "\n" + message_notes
    await botmessage.edit(
        content=content,
        embeds=embeds,
        components=components,
        files=uploaded_files,
        suppress_embeds=True, # Looks not good with too many uploaded pics
        )

@bot.command(
    name="draw",
    description="Draws a picture for you!",
    options = [
        interactions.Option(
            name="prompt",
            description="Words that describe the image",
            type=interactions.OptionType.STRING,
            required=True,
        ),
        interactions.Option(
            name="seed",
            description="Seed, if you want to recreate a specific image",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="quantity",
            description="Amount of images that will be drawn",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="negative_prompt",
            description="Things you dont want to see in the image",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        #interactions.Option(
            #name="apply_caption",
            #description="If the generated image should contain a caption of the prompt",
            #type=interactions.OptionType.BOOLEAN,
            #required=False,
        #),
    ],
)
async def draw(ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = ""): #, apply_caption: bool = False):
    await draw_image(ctx=ctx, prompt=prompt, seed=seed, quantity=quantity, negative_prompt=negative_prompt)
    
# Buttons for the pretty print 
@bot.component("same_prompt_again")
async def button_same_prompt_again(ctx):
    original_message = ctx.message
    
    # No need to check the original attachments for now, just parse the string
    #for attachment in original_message.attachments:
        #print("attachment found")
    prompt, seed, quantity, negative_prompt = parse_command_string(original_message.content.partition('\n')[0]) # Only first line counts
    new_seed = -1
    
    message_notes = "||*Requested from @" + ctx.user.username + "#" + ctx.user.discriminator + " by tapping 'Try again'!*||"
    await draw_image(ctx=ctx, prompt=prompt, seed=new_seed, quantity=quantity, negative_prompt=negative_prompt, message_notes=message_notes)
    
@bot.component("change_prompt")
async def button_change_prompt(ctx):
    original_message = ctx.message
    
    # No need to check the original attachments for now, just parse the string
    prompt, seed, quantity, negative_prompt = parse_command_string(original_message.content.partition('\n')[0])
    
    # Asking the user for a new prompt
    modal = interactions.Modal(
        title="Enter new prompt!",
        custom_id="modal_change_prompt",
        components=[interactions.TextInput(
                        style=interactions.TextStyleType.SHORT,
                        label="Edit prompt",
                        custom_id="text_input_prompt",
                        value=prompt,
                        required=True
                        ),
                    interactions.TextInput(
                        style=interactions.TextStyleType.SHORT,
                        label="Edit negative prompt (optional)",
                        custom_id="text_input_negative_prompt",
                        value=negative_prompt,
                        required=False,
                        min_length=0
                        )
                   ]
                   ,
    )   

    await ctx.popup(modal)

@bot.modal("modal_change_prompt")
async def modal_change_prompt(ctx, new_prompt: str, new_negative_prompt: str):
    original_message = ctx.message
    # Take the old values for seed and quantity
    prompt, seed, quantity, negative_prompt = parse_command_string(original_message.content.partition('\n')[0])
    
    message_notes = "||*Requested from @"  + ctx.user.username + "#" + ctx.user.discriminator + " by tapping 'Keep seed, modify prompt'!*||"
    await draw_image(ctx=ctx, prompt=new_prompt, seed=seed, quantity=quantity, negative_prompt=new_negative_prompt, message_notes=message_notes)
    

# Mode is either "tags" or "desc"
async def interrogate_image(ctx, mode):
    botmessage = await ctx.send(f"Checking image...")
    
    descriptions = []
    # Check all attachments and all embeds
    total_possible_images = len(ctx.target.attachments) + len(ctx.target.embeds)
    if total_possible_images == 0:
        await botmessage.edit("No images found!")
    else:
        image_counter = 0
        for attachment in ctx.target.attachments:
            image_counter += 1
            await botmessage.edit(f"Checking attachment {image_counter} of {total_possible_images}...")
            
            # Is this an image?
            if attachment.filename.endswith(".png") or attachment.filename.endswith(".jpg"):
                # Call the interface service
                description = await interface_interrogate_url(attachment.url, mode)
                if not description:
                    continue
                    
                # Multiple images?
                if total_possible_images > 1:
                    description = "Image " + str(len(descriptions) + 1) + ": " + description
                
                # Save description
                descriptions.append(description)
            
        for embed in ctx.target.embeds:
            image_counter += 1
            await botmessage.edit(f"Checking embed {image_counter} of {total_possible_images}...")
            
            # Is an image embedded?
            if embed.image and embed.image.url:
                print(embed.image.url)
                # Call the interface service
                description = await interface_interrogate_url(embed.image.url, mode)
                if not description:
                    continue
                
                # Multiple images?
                if total_possible_images > 1:
                    description = "Image  " + str(len(descriptions) + 1) + ": " + description
                
                # Save description
                descriptions.append(description)

    # Delete original bot message and make a new one as reply
    await botmessage.delete("Temporary bot message deleted")
    if len(descriptions) > 0:
        descriptions.append("||*Requested from @"  + ctx.user.username + "#" + ctx.user.discriminator + " by holding tap or rightclick!*||")
        await ctx.target.reply("\n".join(descriptions))
        
        
@bot.command(
    type=interactions.ApplicationCommandType.MESSAGE,
    name="Tag this image!"
)
async def get_image_tags(ctx):
    await interrogate_image(ctx, "tags")
        
@bot.command(
    type=interactions.ApplicationCommandType.MESSAGE,
    name="Describe this image!"
)
async def get_image_description(ctx):
    await interrogate_image(ctx, "desc")

@bot.event
async def on_start():
    print("Bot is running!")
    #loop = asyncio.get_event_loop()
    #loop.create_task(check_and_generate())

#async def check_and_generate():
        #print("loop running")
        #time.sleep(1)

print("Waiting for webui to start...", end="")
while True:
    try:
        requests.get("http://localhost:7860/")
        break
    except:
        print(".", end="")
        time.sleep(5)

bot.start()
