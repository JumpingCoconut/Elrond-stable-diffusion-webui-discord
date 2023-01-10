import base64
import datetime
import logging
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
import textwrap
from  elrond_sd_interface import *

# load env variables
config = dotenv_values('.env')

bot = interactions.Client(
    token=config['DISCORD_TOKEN'],
    #logging =logging.DEBUG,
)
debug_mode=bool(config['DEBUG_MODE'] == "True")
config_upscale_size=int(config['UPSCALE_SIZE']) # Set to 1 for no upscaling
config_upscaler=str(config['UPSCALER'])
hive_active=bool(config['HIVEMIND'] == "True")
log_usernames=bool(config['LOG_USERNAMES'] == "True")

# To use files in CommandContext send, you need to load it as an extension.
bot.load("interactions.ext.files")
# Internal use only
hive = None
if hive_active:
    bot.load("elrond_hive")
    hive = bot.get_extension("Hive")

# Using the discord file class, needed for the extension ext.files
def base64_image_to_discord_image(encoded_image, filename):
    # a base64 encoded string starting with "data:image/png;base64," prefix. Remove the prefix
    z = encoded_image[encoded_image.find(',') + 1:]
    
    if debug_mode:
        with open(".debug.uploaded_discord_image.png", "wb") as fh:
            fh.write(base64.b64decode(z))
    
    # Convert it into a discord file for later uploading them in bulk
    fxy = interactions.File(
        filename=filename,  
        fp=base64.b64decode(z)
        )
    return fxy

# Discord messages have bold, cursive etc. Escape these characters. Also accepts a maximum string length, useful because discord limits some strings to 1024 in length.
def escape_discord_markdown(content, max_len=None):
    for ch in ["*", "_", "~", "`"]:
        content = content.replace(ch, "\\" + ch)
    if max_len:
        content = textwrap.shorten(content, width=max_len, placeholder="...") 
    return str(content)

# Create a string like this: /draw prompt:Elrond sitting seed:123456789 quantity:2 negative_prompt:chair, bed
def create_command_string(prompt, seed, quantity, negative_prompt, img2img_url, denoising_strength):
    command_string = "/draw prompt:" + prompt + " seed:" + str(seed) + " quantity:" + str(quantity)
    if negative_prompt:
        command_string = command_string + " negative_prompt:" + negative_prompt
    if img2img_url:
        command_string = command_string + " img2img_url:" + img2img_url
        command_string = command_string + " denoising_strength:" + str(denoising_strength)
    return command_string
    
# Parse an embed for the image generation data. Takes an discord message object to go through the embeds
def parse_embeds_in_message(message):
    prompt = ""
    seed = -1
    quantity = 1
    negative_prompt = ""
    img2img_url = ""
    denoising_strength = 60
    # Do we even have embeds here?
    if message.embeds:
        if len(message.embeds) > 0:
            quantity = len(message.embeds) # Usually we get one embed per image
            # The generation data are hidden in the embedded object! Try to extract them
            for embed in message.embeds:
                # Check the embed custom defined fields
                if embed.fields:
                    for field in embed.fields:
                        if field.name == "Negative prompt":
                            negative_prompt = field.value
                        elif field.name == "Quantity":
                            quantity = int(field.value) 
                        # We display it as a percentage value, but in fact its a decimal. Later converted
                        elif field.name == "Denoising strength":
                            denoising_strength = int(field.value)
                # seed = The image footer
                if embed.footer:
                    if embed.footer.text:
                        seed = int(embed.footer.text)
                # prompt is in the image description
                if embed.description:
                    # In old versions of the bot, the description containe the negative prompt instead. The real prompt was in the title
                    if embed.description[0:16] == "Negative prompt:" and negative_prompt == "":
                        negative_prompt = embed.description[17:] # Starts with "Negative prompt: " so skip the first 17 characters
                    else:
                        prompt = embed.description
                # In old versions of the bot, the prompt was in the title
                if prompt == "":
                    if embed.title:
                        prompt = embed.title
                # If it is img2img mode, the original image is in the thumbnail
                if embed.thumbnail:
                    if embed.thumbnail.url:
                        img2img_url = embed.thumbnail.url
                    # Didnt work? Try the proxy url
                    elif embed.thumbnail.proxy_url:
                        img2img_url = embed.thumbnail.proxy_url
                # Only the first embed is useful for now. The other embeds dont contain any important information that cant be derived from the first embed.
                break
    return prompt, seed, quantity, negative_prompt, img2img_url, denoising_strength
    
# Stupid little function that just takes a letter and makes it a color
def assign_color_to_user(username):
        username_as_color_int = int(ord(username[0])) % 7
        color = interactions.Color.red() # Default
        if username_as_color_int == 0: 
            color = interactions.Color.blurple()
        elif username_as_color_int == 1: 
            color = interactions.Color.green()
        elif username_as_color_int == 2: 
            color = interactions.Color.yellow()
        elif username_as_color_int == 3: 
            color = interactions.Color.fuchsia()
        elif username_as_color_int == 4: 
            color = interactions.Color.red()
        elif username_as_color_int == 5: 
            color = interactions.Color.white()
        elif username_as_color_int == 6: 
            color = interactions.Color.black()
        return color

async def draw_image(ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = "", img2img_url: str = "", denoising_strength = 60, host: str = None):
    if log_usernames:
        print("Request by " + ctx.user.username + "#" + ctx.user.discriminator)
    
     # If we are in img2img mode, first check if the given image can be downloaded
    img2img_mode = False
    if img2img_url != "":
        img2img_image_data = await download_image_from_url(img2img_url)
        img2img_mode = True
        # Cancel if there is no image
        if img2img_image_data == "":
            await ctx.send("No images found!", ephemeral=True)
            return

    # Keep quantity low. Even 9 is pushing it
    if quantity < 1 or quantity > 9:
        quantity = 9

    # The seperator "|" creates multiple images. For every "|" we get exponentially more images. Limit it to four  which makes 4 images.
    if "|" in prompt:
        max_pipes = 4
        too_many_pipes = prompt.count("|") - max_pipes
        if too_many_pipes > 0:
            prompt = prompt.replace("|", ",", too_many_pipes)
            
    # The denoising strength is in fact a decimal value between 0.1 and 0.9. The user gives us a value between 1 and 99. Divide that by 100
    denoising_strength_decimal = 0.6
    if img2img_mode:
        if denoising_strength < 1 or denoising_strength > 99:
            denoising_strength = 60
        try:
            denoising_strength_decimal = float(denoising_strength) / 100.00
        except ValueError:
            pass
    
    # We need to know the seed for later use
    if seed == -1:
        seed = random.randint(0, 999999999)
        
    # Prepare an embed and send a pretty message that we started working
    fields = []
    if negative_prompt != "":
        fields.append(interactions.EmbedField(name="Negative prompt",value=negative_prompt,inline=True))
    # Does this embed contain just one image or multiple?
    if quantity > 1:
        fields.append(interactions.EmbedField(name="Quantity",value=str(quantity),inline=True))
    # In image to image mode, we also have a denoising strength
    if img2img_mode:
        fields.append(interactions.EmbedField(name="Denoising strength",value=denoising_strength,inline=True))
    title = ""
    if img2img_mode:
        title = "Redrawing..." 
    else:
        title = "Drawing..."
    main_embed = interactions.Embed(
                    title=title,
                    description=prompt,
                    timestamp=datetime.datetime.utcnow(), 
                    color=assign_color_to_user(ctx.user.username),
                    footer=interactions.EmbedFooter(text=str(seed)),
                    provider=interactions.EmbedProvider(name="stable-diffusion, elrond, waifu-diffusion, other"),
                    author=interactions.EmbedAuthor(name=ctx.user.username + "#" + ctx.user.discriminator),
                    fields=fields
                    )
    # If it is img2img mode, show the original image in the upper right corner as Thumbnail
    if img2img_mode:
        main_embed.set_thumbnail(img2img_url)
    # Even though drawing isn't finished, we already have all information to allow redraw, edit and copy. These options dont need a finished picture
    b1 = Button(style=1, custom_id="same_prompt_again", label="Try again!")
    b2 = Button(style=3, custom_id="change_prompt", label="Edit")
    b3 = Button(style=2, custom_id="send_command_string", label="Copy")
    # Delete needs a finished picture, add that option later
    b4 = Button(style=4, custom_id="delete_picture", label="Delete (...)", disabled=True)
    components = spread_to_rows(b1, b2, b3, b4)#, s1)
    # Note: the maximum embed length of all fields combined is 6000 characters. We dont check that because we are lazy as fuck
    botmessage = await ctx.send(embeds=[main_embed], components=components)

    # Get data via web request. Image to image mode or text to image mode?
    encoded_images = []
    if img2img_mode:
        encoded_images = await interface_img2img(prompt=prompt, seed=seed, quantity=quantity, negative_prompt=negative_prompt, img2img_image_data=img2img_image_data, denoising_strength=denoising_strength_decimal, host=host)
    else:
        encoded_images = await interface_txt2img(prompt=prompt, seed=seed, quantity=quantity, negative_prompt=negative_prompt, host=host)
    
    # No result?
    if len(encoded_images) == 0:
        main_embed.title = "Drawing failed."
        await botmessage.edit(embeds=[main_embed], components=components)
        return

    # If its multiple images, then the first one sent will be a grid of all other images combined
    multiple_images_as_one = False
    if len(encoded_images) > 1:
        # User requested 4 or more images, ONLY send the comprehensive preview grid so the message doesnt bloat up
        if quantity >= 4 or "|" in prompt:
            encoded_images = [encoded_images[0]]
            multiple_images_as_one = True
        else:
            # Otherwise, skip the preview grid (first entry of this list)
            encoded_images.pop(0)

    # Do we upscale later?
    upscale_later = True
    if multiple_images_as_one:
        # Dont upscale, its big enough
        upscale_later = False
    elif config_upscale_size <= 1:
        # Dont upscale, size 1 makes no sense
        upscale_later = False
  
    # Prepare all images for discord, upload them, put them in embeds
    files_to_upload = []
    embeds = [main_embed]
    for i, encoded_image in enumerate(encoded_images):
        # The seed given is just the starting seed for the first image, all other images have ongoing numbers
        current_seed = seed + i

        # Filename for upload.
        filename = str(current_seed) + ".png"
        
        # Convert the base64 image to a discord file and save it in a list to upload later
        files_to_upload.append(base64_image_to_discord_image(encoded_image=encoded_image, filename=filename))
    
        # Add the generated file to the latest embed
        embeds[i].set_image(url="attachment://" + filename)

        # Set the image title
        title = ""
        if upscale_later:
            title += "(Preview) "
        if img2img_mode:
            title += "Redraw: "
        if len(encoded_images) > 1:
            title += f"[{i+1} of {len(encoded_images)}]: "
        title += prompt
        title = textwrap.shorten(title, width=60, placeholder="...")
        # [0:256] is the maximum title length it looks stupid, make the title shorter
        embeds[i].title = title

        # If there are more pictures on the way, prepare the next embed with some filler text. Sub-embeds only need seed, thumbnail and timestamp.
        if i+1 < len(encoded_images):
            next_embed = interactions.Embed(
                            timestamp=datetime.datetime.utcnow(), 
                            color=assign_color_to_user(ctx.user.username),
                            footer=interactions.EmbedFooter(text=str(current_seed + 1)),
                            )
            if img2img_mode:
                next_embed.set_thumbnail(img2img_url)
            embeds.append(next_embed)

    # Make the images bigger if neccessary
    if upscale_later:
        for i, encoded_image in enumerate(encoded_images):
            # Working message
            embeds[i].title = f"Upscaling image {i+1} of {len(encoded_images)}..."
            await botmessage.edit(embeds=embeds, files=files_to_upload, components=components)
            # Call the upscaler
            upscaler=config_upscaler
            if not upscaler:
                upscaler = "None"
            upscaled_image = await interface_upscale_image(encoded_image=encoded_image, size=config_upscale_size, upscaler=upscaler) # a base64 encoded string starting with "data:image/png;base64," prefix
            # Filename for upload.
            current_seed = seed + i
            filename = str(current_seed) + ".png"
            # Replace the old and small image with the new and big image
            files_to_upload[i] = base64_image_to_discord_image(encoded_image=upscaled_image, filename=filename)
            # Restore the image title
            title = ""
            if img2img_mode:
                title += "Redraw: "
            if len(encoded_images) > 1:
                title += f"[{i+1} of {len(encoded_images)}]: "
            title += prompt
            title = textwrap.shorten(title, width=60, placeholder="...")
            embeds[i].title = title

    # Now enable the delete button and send the finished message
    b4.disabled = False
    b4.label = "Delete"
    #s1 = SelectMenu(
        #custom_id="s1",
        #options=[
            #SelectOption(label="Redraw picture (low similarity)", value="75"),
            #SelectOption(label="Redraw picture (high similarity)", value="20"),
        #],
    #)    
    components = spread_to_rows(b1, b2, b3, b4)#, s1)
    await botmessage.edit(
        content="",
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
            min_length=0,
            max_length=1024, # 1024 In theory, but we string all fields together later so dont overdo it
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
            min_length=0,
            max_length=1024, # 1024 In theory, but we string all fields together later so dont overdo it
            required=False,
        ),
        interactions.Option(
            name="img2img_attachment",
            description="Image to image generation, take this as base",
            type=interactions.OptionType.ATTACHMENT,
            required=False,
        ),
        interactions.Option(
            name="denoising_strength",
            description="For img2img. How much should the newly dran image diverge from the given image? 99=Highest",
            type=interactions.OptionType.INTEGER,
            required=False,
            min_length=0,
            max_length=2, 
        ),
        interactions.Option(
            name="img2img_url",
            description="For image to image mode, optional",
            type=interactions.OptionType.STRING,
            required=False,
        ),        
    ],
)
async def draw(ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = "", img2img_attachment: str = "", img2img_url: str = "", denoising_strength: int = 0):
    host = None
    if hive_active:
        host = hive.get_random_client()
    
    host_url = config["GRADIO_API_BASE_URL"] if host == None else host.url

    # If the user uploaded an attachment, take that instead of the img2img url. 
    if img2img_attachment:
        if img2img_attachment.url:
            img2img_url = img2img_attachment.url
    await draw_image(ctx=ctx, prompt=prompt, seed=seed, quantity=quantity, negative_prompt=negative_prompt, img2img_url=img2img_url, denoising_strength=denoising_strength, host=host_url)
    
# Buttons for the pretty print 
@bot.component("same_prompt_again")
async def button_same_prompt_again(ctx):
    original_message = ctx.message
    # The generation data are hidden in the embedded object
    prompt, seed, quantity, negative_prompt, img2img_url, denoising_strength = parse_embeds_in_message(original_message)
    # Give a new seed
    new_seed = -1
    await draw_image(ctx=ctx, prompt=prompt, seed=new_seed, quantity=quantity, negative_prompt=negative_prompt, img2img_url=img2img_url, denoising_strength=denoising_strength)
    
@bot.component("change_prompt")
async def button_change_prompt(ctx):
    original_message = ctx.message
    # The generation data are hidden in the embedded object
    prompt, seed, quantity, negative_prompt, img2img_url, denoising_strength = parse_embeds_in_message(original_message)
    # Asking the user for a new prompt. Img2img mode or txt2img mode?
    modal = None
    if img2img_url == "":
        modal = interactions.Modal(
                title="Edit prompt",
                custom_id="modal_edit",
                components=[interactions.TextInput(
                                style=interactions.TextStyleType.PARAGRAPH,
                                label="Prompt",# Words that describe the image.",
                                custom_id="text_input_prompt",
                                value=prompt,
                                min_length=1,
                                max_length=1024, # 1024 In theory, but we string all fields together later so dont overdo it
                                required=True
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.PARAGRAPH,
                                label="Negative prompt",# Things you dont want to see in the image.",
                                placeholder="optional",
                                custom_id="text_input_negative_prompt",
                                value=negative_prompt,
                                min_length=0,
                                max_length=1024, # 1024 In theory, but we string all fields together later so dont overdo it
                                required=False,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Seed",# Changing it makes a completely different picture.",
                                placeholder="leave empty for random seed",
                                custom_id="text_input_seed",
                                value=seed,
                                min_length=0,
                                max_length=9,
                                required=False,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Quantity",
                                placeholder="optional",
                                custom_id="text_input_quantity",
                                value=quantity,
                                min_length=0,
                                max_length=1,
                                required=False,
                                )
                            ]
                        ,
                )   
    else:
        modal = interactions.Modal(
                title="Redraw original image",
                custom_id="modal_redraw",
                components=[interactions.TextInput(
                                style=interactions.TextStyleType.PARAGRAPH,
                                label="Prompt",# Words that describe the image.",
                                custom_id="text_input_prompt",
                                value=prompt,
                                min_length=1,
                                max_length=1024, # 1024 In theory, but we string all fields together later so dont overdo it
                                required=True
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.PARAGRAPH,
                                label="Negative prompt",# Things you dont want to see in the image.",
                                placeholder="optional",
                                custom_id="text_input_negative_prompt",
                                value=negative_prompt,
                                min_length=0,
                                max_length=1024, # A little bit shorter than normal so we have space for the URL
                                required=False,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Seed",# Changing it makes a completely different picture.",
                                placeholder="leave empty for random seed",
                                custom_id="text_input_seed",
                                value=seed,
                                min_length=0,
                                max_length=9,
                                required=False,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Original Image URL",
                                # Todo: This is the edit button. Let the user just choose between the old pic, or the new pic. (imgurl or thumbnail-url)
                                # The rest is too confusing
                                placeholder="https://example.com/yourimage.jpg",
                                custom_id="text_input_image_url",
                                value=img2img_url,
                                min_length=1,
                                max_length=1024, # URLs can be 2048 characters long, discord fields 1024, but we only have 1024 in total for ALL fields...
                                required=True,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Denoising strength %",
                                placeholder="Divergence rate (99=highest)",
                                custom_id="text_input_denoising_strength",
                                value=denoising_strength,
                                min_length=0,
                                max_length=2,
                                required=False,
                                )
                            ]
                        ,
                )   
    await ctx.popup(modal)

@bot.modal("modal_edit")
async def modal_edit(ctx, new_prompt: str, new_negative_prompt: str, new_seed: str, new_quantity: str):
    original_message = ctx.message
    # Check if new seed is valid
    seed = -1
    try:
        seed = int(new_seed)
    except ValueError:
        pass
    if seed < 1 or seed > 999999999:
        seed = random.randint(0, 999999999)
    # Check if quantity is valid
    quantity = 1
    try:
        quantity = int(new_quantity)
    except ValueError:
        pass
    if quantity < 1 or quantity > 9:
        quantity = 1
    # Generate again
    await draw_image(ctx=ctx, prompt=new_prompt, seed=seed, quantity=quantity, negative_prompt=new_negative_prompt)
    
@bot.component("send_command_string")
async def button_send_command_string(ctx):
    original_message = ctx.message
    # Get the command string
    prompt, seed, quantity, negative_prompt, img2img_url, denoising_strength = parse_embeds_in_message(original_message)
    command_string = create_command_string(escape_discord_markdown(prompt), seed, quantity, escape_discord_markdown(negative_prompt), img2img_url, denoising_strength)
    # Post it as private reply inside an embed for easy copying. Embeds have a copy feature on mobile
    content = None
    fields = []
    # Embeds only support text up to 1024 characters in size. If its more, send it as content, even though its ugly
    if len(command_string) > 1024:
        if len(command_string) > 2000:
            content = "This /draw command is too big to copy because discord messages can only be 2000 characters long. Try copying the prompt, seed and negative prompt manually."
        else:
            content = command_string
    else:
        fields.append(interactions.EmbedField(name="You can recreate this image with:",value=command_string))
    output_embed = interactions.Embed(fields=fields)
    # Set original image as thumbnail 
    for embed in original_message.embeds:
        if embed.image:
            if  embed.image.url:
                output_embed.set_thumbnail(embed.image.url)
    if len(output_embed.fields) > 0 or output_embed.thumbnail:
        await ctx.send(content=content, embeds=[output_embed], ephemeral=True) 
    else:
        await ctx.send(content=content, ephemeral=True) 

@bot.component("delete_picture")
async def button_delete_picture(ctx):
    original_message = ctx.message
    # Only delete the post if the current user is the author
    current_user = ctx.user.username + "#" + ctx.user.discriminator
    author = ""
    new_embeds = []
    # Check all embeds and copy them, but without the image. Also check if they are from the correct author
    for embed in original_message.embeds:
        if embed.author: 
            if embed.author.name:
                if  author == "":
                    author = embed.author.name
                # Only the author can delete its own post
                elif author != embed.author.name:
                    break
        # Make a new embed, but this time, without the Image
        if embed.image:
            if  embed.image.url:
                embed.image.url = None
            if embed.image.proxy_url:
                embed.image.proxy_url = None
        embed.title = "Image deleted by author"
        new_embeds.append(embed)
    if author != current_user:
        print(current_user + " tried to delete an image of " + author)
        await ctx.send("You can't delete this post because it is not your post. Ask a moderator or admin to delete it.", ephemeral=True) 
    else:
        # Add a "Restore" button in case the user changes its mind
        b3 = Button(style=2, custom_id="send_command_string", label="Restore")
        # Replace the embeds by the new one which doesnt contain the picture. Also delete the pictures from the message attachments (discord server)
        await ctx.edit(files=[], attachments=[], embeds=new_embeds, components=[b3])
        return
    
# Mode is either "tags" or "desc"
async def get_images_from_message(ctx):
    # Check all attachments and all embeds
    found_images = []
    for attachment in ctx.attachments:
        # Is this an image?
        if attachment.filename.endswith(".png") or attachment.filename.endswith(".jpg"):
            found_images.append(attachment.url)
    for embed in ctx.embeds:
        if embed.image:
            if  embed.image.url:
                found_images.append(embed.image.url)
            # Didnt work? Try the proxy url
            elif embed.image.proxy_url:
                found_images.append(embed.image.proxy_url)
        # Now try the thumbnails if the normal images didnt work
        elif embed.thumbnail:
            if embed.thumbnail.url:
                found_images.append(embed.thumbnail.url)
            elif embed.thumbnail.proxy_url:
                found_images.append(embed.thumbnail.proxy_url)
    return found_images
        
# Mode is either "tags" or "desc"
async def interrogate_image(ctx, mode):
    # Debug: What metadata do we have in attachments and embeds?
    if debug_mode:
        for attachment in ctx.target.attachments:
            print("attachment found")
        for embed in ctx.target.embeds:
            print("embed found")
            # print(embed._json) Nice for debugging, just prints everything
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
            if embed.thumbnail:
                if embed.thumbnail.url:
                    print("embed thumbnail url: " + embed.thumbnail.url)
                if embed.thumbnail.proxy_url:
                    print("embed thumbnail proxy_url: " + embed.thumbnail.proxy_url)
            if embed.provider: 
                print("embed provider found")
                if embed.provider.name:
                    print("embed provider name: " + str(embed.provider.name))
            if embed.author: 
                print("embed author found")
                if embed.author.name:
                    print("embed author name: " + str(embed.author.name))
            if embed.fields:
                for field in embed.fields:
                    name = ""
                    value = ""
                    if field.name:
                        name = str(field.name)
                    if field.value:
                        value = str(field.value)
                    print("embed field [" + name + "]: " + value)
    # Get all images from this message
    image_urls = await get_images_from_message(ctx.target)
    if len(image_urls) == 0:
        await ctx.send("No images found!", ephemeral=True)
        return
    
    # For every found image we will generate one new tiny embed with thumbnail etc
    botmessage = await ctx.send(embeds=[interactions.Embed(title="Checking image...")])
    output_embeds = []
        
    # Check all attachments and all embeds
    for i, image_url in enumerate(image_urls):
        # Temporary placeholder embed
        output_embed = interactions.Embed(
                            title=f"Checking attachment {int(i+1)} of {len(image_urls)}...", 
                            timestamp=datetime.datetime.utcnow(), 
                            color=assign_color_to_user(ctx.user.username),
                            thumbnail=interactions.EmbedImageStruct(url=image_url),
                            provider=interactions.EmbedProvider(name=mode),
                            author=interactions.EmbedAuthor(name=ctx.user.username + "#" + ctx.user.discriminator),
                            )
        await botmessage.edit(embeds=(output_embeds + [output_embed]))
        # Call the interface service
        description = await interface_interrogate_url(image_url, mode)
        if description:
            # Finalize the embed
            output_embed.title = None
            output_embed.description = escape_discord_markdown(description, 1024)
            # Save description
            output_embeds.append(output_embed)

    # Delete original bot message and make a new one as reply
    await botmessage.delete("Temporary bot message deleted")
    if len(output_embeds) > 0:
        await ctx.target.reply(embeds=output_embeds)
        
@bot.command(
    type=interactions.ApplicationCommandType.MESSAGE,
    description="Booru-style tag description",
    name="Generate tags"
)
async def get_image_tags(ctx):
    await interrogate_image(ctx, "tags")
        
@bot.command(
    type=interactions.ApplicationCommandType.MESSAGE,
    description="Describe image in words",
    name="Generate text"
)
async def get_image_description(ctx):
    await interrogate_image(ctx, "desc")
        
@bot.command(
    type=interactions.ApplicationCommandType.MESSAGE,
    description="Make any image bigger",
    name="Upscale Image"
)
async def upscale_image(ctx):
    # Get all images from this message
    image_urls = await get_images_from_message(ctx.target)
    if len(image_urls) == 0:
        await ctx.send("No images found!", ephemeral=True)
        return
    
    # For every found image we will generate one new tiny embed with thumbnail etc
    botmessage = await ctx.send(embeds=[interactions.Embed(title="Checking image...")])
    output_embeds = []
    files_to_upload = []
        
    # Check all attachments and all embeds
    for i, image_url in enumerate(image_urls):
        # Temporary placeholder embed
        output_embed = interactions.Embed(
                            title=f"Upscaling image {int(i+1)} of {len(image_urls)}...",
                            description="Discord automatically deletes images over a certain size. If this message disappears after upscaling, discord decided the image is too big. Try smaller images then.",
                            timestamp=datetime.datetime.utcnow(), 
                            color=assign_color_to_user(ctx.user.username),
                            thumbnail=interactions.EmbedImageStruct(url=image_url),
                            provider=interactions.EmbedProvider(name="upscaler"),
                            author=interactions.EmbedAuthor(name=ctx.user.username + "#" + ctx.user.discriminator),
                            )
        await botmessage.edit(embeds=(output_embeds + [output_embed]),files=files_to_upload)
        # Download the image
        encoded_image = await download_image_from_url(image_url)
        # Call the interface service, upscale it by factor two. Also make sure an upscaler is selected
        upscaler=config_upscaler
        if not upscaler:
            upscaler = "SwinIR_4x"
        upscaled_image = await interface_upscale_image(encoded_image, size=2, upscaler=upscaler)
        # Filename for upload.
        filename = "upscaler_" + str(i) + ".png"
        # List of files to upload to the discord server
        files_to_upload.append(base64_image_to_discord_image(encoded_image=upscaled_image, filename=filename))
        # Show the image in the embed, and update embed title
        output_embed.title = f"Upscaled image {int(i+1)} of {len(image_urls)}"
        output_embed.set_image(url="attachment://" + filename)
        output_embed.description = None
        output_embeds.append(output_embed)

    # Delete original bot message and make a new one as reply
    await botmessage.delete("Temporary bot message deleted")
    if len(output_embeds) > 0:
        try: 
            await ctx.target.reply(embeds=output_embeds,files=files_to_upload)
        except interactions.api.error.LibraryException:
            # Image too large for discord. Remove the uploaded images and show error message.
            error_embeds = []
            for embed in output_embeds:
                embed.set_image(None)
                embed.title = "Could not post upscaled image"
                embed.description = "Discord wont allow us to post the message. Upscaling was successful, but the result was too large to post it. Try smaller images."
                error_embeds.append(embed)
            await ctx.send(embeds=error_embeds, ephemeral=True)

@bot.command(
    type=interactions.ApplicationCommandType.MESSAGE,
    description="Create img from img",
    name="Redraw"
)
@autodefer() # Can take a while to download an image, in that case automatically send a dummy reply so discord doesnt abort us
async def redraw_image(ctx):
    img_urls = await get_images_from_message(ctx.target)
    if len(img_urls) == 0:
        await ctx.send("No images found!", ephemeral=True)
        return
    if len(img_urls) > 0:
        # It could be our own old message. In that case we have some metadata there.
        prompt, seed, quantity, negative_prompt, img2img_url, denoising_strength = parse_embeds_in_message(ctx.target)
        if seed == -1:
            seed = 0
        # Now iterate all images found before. Dont use the img2img_url from the embed, because there wont always be an embed when right-clicking on random images.
        for img_url in img_urls:
            # Bring one popup for every image and give the user options
            modal = interactions.Modal(
                title="Redraw image",
                custom_id="modal_redraw",
                components=[interactions.TextInput(
                                style=interactions.TextStyleType.PARAGRAPH,
                                label="Prompt",# Words that describe the image.",
                                custom_id="text_input_prompt",
                                value=prompt,
                                min_length=1,
                                max_length=1024, # 1024 In theory, but we string all fields together later so dont overdo it
                                required=True
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.PARAGRAPH,
                                label="Negative prompt",# Things you dont want to see in the image.",
                                placeholder="optional",
                                custom_id="text_input_negative_prompt",
                                value=negative_prompt,
                                min_length=0,
                                max_length=1024, # A little bit shorter than normal so we have space for the URL
                                required=False,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Seed",# Changing it makes a completely different picture.",
                                placeholder="leave empty for random seed",
                                custom_id="text_input_seed",
                                value=seed,
                                min_length=0,
                                max_length=9,
                                required=False,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Image URL",
                                placeholder="https://example.com/yourimage.jpg",
                                custom_id="text_input_image_url",
                                value=img_url,
                                min_length=1,
                                max_length=1024, # URLs can be 2048 characters long, discord fields 1024, but we only have 1024 in total for ALL fields...
                                required=True,
                                ),
                            interactions.TextInput(
                                style=interactions.TextStyleType.SHORT,
                                label="Denoising strength %",
                                placeholder="Divergence rate (99=highest)",
                                custom_id="text_input_denoising_strength",
                                value=denoising_strength,
                                min_length=0,
                                max_length=2,
                                required=False,
                                )
                        ]
                        ,
            )   
            await ctx.popup(modal)
            # Actually, discord stops us from bombarding the user with popups. So he just gets the first image and thats it.
            break

# Modal for redrawing an image
@bot.modal("modal_redraw")
async def modal_redraw(ctx, new_prompt: str, new_negative_prompt: str, new_seed: str, new_image_url: str, new_denoising_strength):
    # Check if new seed is valid
    seed = -1
    try:
        seed = int(new_seed)
    except ValueError:
        pass
    if seed < 1 or seed > 999999999:
        seed = random.randint(0, 999999999)
    # Denoising strength is actually a float between 0.1 and 0.9. But the user enters a int between 1 and 99
    denoising_strength = 60
    try:
        denoising_strength = int(new_denoising_strength)
    except ValueError:
        pass
    if denoising_strength < 1  or denoising_strength > 99:
        denoising_strength = 60
    # Denoising strength = How different the image can be. 1.0 would be completely unrelated, 0.0 would be the same image as before.
    await draw_image(ctx=ctx, prompt=new_prompt, seed=seed, quantity=1, negative_prompt=new_negative_prompt, img2img_url=new_image_url, denoising_strength=denoising_strength)
    
# # Command for internal use only
# @bot.command(
    # name="draw_devmode",
    # description="Developer version of draw, constantly crashing",
    # scope=844680085298610177,
    # options = [
        # interactions.Option(
            # name="prompt",
            # description="Words that describe the image",
            # type=interactions.OptionType.STRING,
            # min_length=0,
            # max_length=400, # 1024 In theory, but we string all fields together later so dont overdo it
            # required=True,
        # ),
        # interactions.Option(
            # name="seed",
            # description="Seed, if you want to recreate a specific image",
            # type=interactions.OptionType.INTEGER,
            # required=False,
        # ),
        # interactions.Option(
            # name="quantity",
            # description="Amount of images that will be drawn",
            # type=interactions.OptionType.INTEGER,
            # required=False,
        # ),
        # interactions.Option(
            # name="negative_prompt",
            # description="Things you dont want to see in the image",
            # type=interactions.OptionType.STRING,
            # min_length=0,
            # max_length=400, # 1024 In theory, but we string all fields together later so dont overdo it
            # required=False,
        # ),
    # ],
# )
# async def draw_devmode(ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = ""):
    # # Get the function from the test system
    # from elrond_sd_interface_integration_environment import interface_txt2img as integration_environment_interface_txt2img
    # from elrond_sd_interface_integration_environment import interface_upscale_image as  integration_environment_interface_upscale_image
    # # Copy paste the command you want to test here:
    # # ...
        

@bot.event
async def on_start():
    print("Bot is running!")

if hive_active:
    print("Elrond Hivemode active, try reaching hives...")    

print("Waiting for webui " + str(config["GRADIO_API_BASE_URL"]) + " to start...", end="")
while True:
    try:
        requests.get(config["GRADIO_API_BASE_URL"])
        break
    except:
        print(".", end="")
        time.sleep(5)

# local methods are only available to the extension class once passed via the client instance
bot.draw = draw_image
bot.start()

