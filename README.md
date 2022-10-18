# Elrond-stable-diffusion-webui-discord
 Integrates AUTOMATIC1111 stable-diffusion-webui into a discord bot for easily accessible use. 

 Calls [AUTOMATIC1111/stable-diffusion-webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui) and uses it through a discord bot. Add the bot to your server to access the webuis features through slash commands and right-click context menus.

![readme-1.png](readme-1.png)
![readme-1.png](readme-2.png)

It allows the discord users to generate stable diffusion images.

## Features

- Generates images and increases their size via upscaling
- Inspects existing images
- (Future) img2img via rightclick
- Modern discord slash and button interface

## Install and Run

- Install [AUTOMATIC1111/stable-diffusion-webui ](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
- Install [Python 3.10](https://www.python.org/downloads/release/python-3100/)
- Create and invite your discord bot to a server (https://discord.com/developers/applications/). Make sure that under OAuth2, it has at least bot and applications.commands. Example: ![readme-3.png](readme-3.png)
- Write the discord API key in your `.env` configuration file
- use install.bat to automatically install all python requirements in a virtual environment
- *or do it manually by checking requirements.txt*
- (optional) make sure to enable the parameter `--danbooru` in your `AUTOMATIC1111/stable-diffusion-webui/webui-user.bat`
- run your `AUTOMATIC1111/stable-diffusion-webui/webui-user.bat`
- use `run-elrond.bat` to start the bot
- *or start it manually by starting `elrond.py`*
