import base64
import datetime
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
debug_mode=bool(config['DEBUG_MODE'])

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
    
# Parse an embed for the image generation data. Takes an discord message object to go through the embeds
def parse_embeds_in_message(message):
    prompt = ""
    seed = -1
    quantity = 1
    negative_prompt = ""
    # The generation data are hidden in the embedded object! Try to extract them
    for embed in message.embeds:
        # prompt = The image title
        if embed.title:
            prompt = embed.title
        # negative prompt = The image title
        if embed.description:
            negative_prompt = embed.description
            # Starts with "Negative prompt: " so skip the first 17 characters
            negative_prompt = negative_prompt[17:]
        # seed = The image footer
        if embed.footer:
            if embed.footer.text:
                seed = int(embed.footer.text)
        # For now, we only care for the first embed and just recreate the others by giving a quantity. This is possible because their seeds consecutive
        quantity = len(message.embeds)
        break
    
    return prompt, seed, quantity, negative_prompt

async def draw_image(ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = ""):
    
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
    files_to_upload = []
    embeds = []
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
        
        # Filename for upload. Make sure its unique (is it really important?)
        filename = str(current_seed) + "-" + str(random.randint(0, 999999999)) + ".png"
        
        if debug_mode:
            with open(".debug.image.png", "wb") as fh:
                fh.write(base64.b64decode(z))
        
        # Convert it into a discord file for later uploading them in bulk
        fxy = interactions.File(
            filename=filename,  
            fp=base64.b64decode(z)
            )
        files_to_upload.append(fxy)

        # Paint the UI pretty
        description = ""
        if negative_prompt != "":
            description = "Negative prompt: " + negative_prompt
        embed = interactions.Embed(
                title=prompt, # Dont change this because this is how we get the data back later
                description=description,
                timestamp=datetime.datetime.utcnow(), 
                color=interactions.Color.red(),
                footer=interactions.EmbedFooter(text=str(current_seed)),
                image=interactions.EmbedImageStruct(url="attachment://" + filename),
                provider=interactions.EmbedProvider(name="stable-diffusion-1-4, waifu-diffusion-1-3, nai, other"),
                author=interactions.EmbedAuthor(name=ctx.user.username + "#" + ctx.user.discriminator),
                #fields=[
                        #interactions.EmbedField(name="prompt",value=prompt,inline=True),
                        #interactions.EmbedField(name="seed",value=str(current_seed),inline=True),
                        #interactions.EmbedField(name="negative prompt",value=negative_prompt,inline=True),
                        #],
                )
        
        embeds.append(embed)

    # User inputs?
    b1 = Button(style=1, custom_id="same_prompt_again", label="Try again!")
    b2 = Button(style=3, custom_id="change_prompt", label="Keep seed, modify prompt")
    b3 = Button(style=4, custom_id="delete_picture", label="Delete")
    #s1 = SelectMenu(
        #custom_id="s1",
        #options=[
            #SelectOption(label="Redraw picture (low similarity)", value="75"),
            #SelectOption(label="Redraw picture (high similarity)", value="20"),
        #],
    #)    
    components = spread_to_rows(b1, b2, b3)#, s1, b3, b4)
    #components = [b1, b2]#, s1, b3, b4)
    
    # Print the string that can be used to replicate this exact picture, for easy copy-paste
    content = "``" + create_command_string(prompt, seed, quantity, negative_prompt) + "``\n"
    await botmessage.edit(
        content=content,
        embeds=embeds,
        components=components,
        files=files_to_upload,
        suppress_embeds=False, 
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
    # The generation data are hidden in the embedded object
    prompt, seed, quantity, negative_prompt = parse_embeds_in_message(original_message)
    # Give a new seed
    new_seed = -1
    await draw_image(ctx=ctx, prompt=prompt, seed=new_seed, quantity=quantity, negative_prompt=negative_prompt)
    
@bot.component("change_prompt")
async def button_change_prompt(ctx):
    original_message = ctx.message
    
    # No need to check the original attachments for now, just parse the string
    prompt, seed, quantity, negative_prompt = parse_embeds_in_message(original_message)
    
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
    prompt, seed, quantity, negative_prompt = parse_embeds_in_message(original_message)
    # We only take the new prompt and negative prompt
    await draw_image(ctx=ctx, prompt=new_prompt, seed=seed, quantity=quantity, negative_prompt=new_negative_prompt)
    
@bot.component("delete_picture")
async def button_change_prompt(ctx):
    original_message = ctx.message
    # Only delete the post if the current user is the author
    current_user = ctx.user.username + "#" + ctx.user.discriminator
    author = ""
    # All embeds should have the same author but just to be sure check all of them.
    for embed in original_message.embeds:
        if embed.author: 
            if embed.author.name:
                if  author == "":
                    author = embed.author.name
                elif author != embed.author.name:
                    break
    if author != current_user:
        print(current_user + " tried to delete an image of " + author)
        await ctx.send("You can't delete this post because it is not your post. Ask a moderator or admin to delete it.", ephemeral=True) 
    else:
        old_messagetext = original_message.content
        await original_message.reply("*This message was deleted on request of " + current_user + ". To recreate it in another channel, use:*\n\n||" + old_messagetext + "||")
        await original_message.delete("Message deleted on request of " + current_user)
        await ctx.send("Post deleted on your request.", ephemeral=True) 

@bot.modal("modal_change_prompt")
async def modal_change_prompt(ctx, new_prompt: str, new_negative_prompt: str):
    original_message = ctx.message
    # Take the old values for seed and quantity
    prompt, seed, quantity, negative_prompt = parse_embeds_in_message(original_message)
    # We only take the new prompt and negative prompt
    await draw_image(ctx=ctx, prompt=new_prompt, seed=seed, quantity=quantity, negative_prompt=new_negative_prompt)
    
# Mode is either "tags" or "desc"
async def interrogate_image(ctx, mode):
    botmessage = await ctx.send(f"Checking image...")
    
    # What metadata do we have in attachments and embeds?
    if debug_mode:
        for attachment in ctx.target.attachments:
            print("attachment found")
        for embed in ctx.target.embeds:
            print("embed found")
            if embed.title :
                print("title: " + embed.title)
            if embed.type:
                print("type: " + str(embed.type))
            if embed.description:
                print("desc: " + embed.description)
            if embed.timestamp:
                print("time: " + str(embed.timestamp))
            if embed.color:
                print("color: " + str(embed.color))
            if embed.footer:
                print("embed footer found")
                if embed.footer.text:
                    print("embed footer text: " + embed.footer.text)
            if embed.image :
                print("embed image found")
                if (embed.image.url):
                    print("embed image url: " + embed.image.url)
                if (embed.image.proxy_url):
                    print("embed image proxy_url: " + embed.image.proxy_url)
            if embed.provider: 
                print("embed provider found")
                if embed.provider.name:
                    print("emed provider name: " + str(embed.provider.name))
            if embed.author: 
                print("embed author found")
                if embed.author.name:
                    print("emed author name: " + str(embed.author.name))
    
    # For every found image we will generate one new tiny embed with thumbnail etc
    output_embeds = []
    color = interactions.Color.red()
    if mode == "desc":
        color = interactions.Color.white()
    elif mode == "tags":
        color = interactions.Color.black()
        
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
                    
                # Paint a pretty embed
                output_embed = interactions.Embed(
                                description=description,
                                timestamp=datetime.datetime.utcnow(), 
                                color=color,
                                thumbnail=interactions.EmbedImageStruct(url=attachment.url),
                                provider=interactions.EmbedProvider(name=mode),
                                author=interactions.EmbedAuthor(name=ctx.user.username + "#" + ctx.user.discriminator),
                                )
                
                # Save description
                output_embeds.append(output_embed)
            
        for embed in ctx.target.embeds:
            image_counter += 1
            await botmessage.edit(f"Checking embed {image_counter} of {total_possible_images}...")
            
            # Is an image embedded?
            description = None
            if embed.image:
                if  embed.image.url:
                    # Call the interface service
                    description = await interface_interrogate_url(embed.image.url, mode)
                # Didnt work? Try the proxy url
                if (not description) and embed.image.proxy_url:
                    description = await interface_interrogate_url(embed.image.proxy_url, mode)
            # Still nothing? Skip this embed
            if not description:
                continue
                
            # Paint a pretty embed
            output_embed = interactions.Embed(
                            description=description,
                            timestamp=datetime.datetime.utcnow(), 
                            color=color,
                            thumbnail=interactions.EmbedImageStruct(url=embed.image.url),
                            provider=interactions.EmbedProvider(name=mode),
                            footer=interactions.EmbedFooter(text="Image check requested by " + ctx.user.username + "#" + ctx.user.discriminator),
                            )
            
            # Save description
            output_embeds.append(output_embed)

    # Delete original bot message and make a new one as reply
    await botmessage.delete("Temporary bot message deleted")
    if len(output_embeds) > 0:
        await ctx.target.reply(embeds=output_embeds)
        
        
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

print("Waiting for webui to start...", end="")
while True:
    try:
        requests.get("http://localhost:7860/")
        break
    except:
        print(".", end="")
        time.sleep(5)

bot.start()
