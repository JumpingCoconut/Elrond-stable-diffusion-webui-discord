import requests
from urllib3.exceptions import HTTPError
from urllib.error import URLError
from urllib.parse import urlparse
import interactions
import datetime
import random

# post /login    username= password=
# cookie "access-token"

# custom Exception classes for more fine-grained error handling
class VersionNotSupportedError(Exception):
    pass

class NoSdWebUiError(Exception):
    def __init__(self, foundver):
        self.foundver = foundver

# object representing individual bot instances (client machines)
class HiveBot():
    def __init__(self, url: str, access_token: str = None, nickname: str = None):
        self.url = url
        self.access_token = access_token
        self.nickname = nickname
        self.dt_added = datetime.datetime.now()

# extension class
class Hive(interactions.Extension):
    def __init__(self, client):
        self.bot: interactions.Client = client
        self.hivebots = list()

    # all this command does is call the "main" draw_image method on a random hivebot machine
    @interactions.extension_command(
        name="draw_hivemind",
        description="Makes someone else draw a picture for you!",
        scope=844680085298610177,
        options = [
                interactions.Option(
                    name="prompt",
                    description="Words that describe the image",
                    type=interactions.OptionType.STRING,
                    min_length=0,
                    max_length=400, # 1024 In theory, but we string all fields together later so dont overdo it
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
                    max_length=400, # 1024 In theory, but we string all fields together later so dont overdo it
                    required=False,
                ),
            ]
        )
    async def draw_hivemind(self, ctx: interactions.CommandContext, prompt: str = "", seed: int = -1, quantity: int = 1, negative_prompt: str = ""):
        try:
            hivebot = random.choice(self.hivebots)
        except IndexError:
                await ctx.send(f"Unfortunately, there are no bots in the hivemind right now", ephemeral=True)     
                return
        #if hivebot.nickname is not None:
        #    await ctx.send(f"Your bot: " + str(hivebot.ip) + ":" + str(hivebot.port) + " as " + hivebot.nickname, ephemeral=True)
        #else:
        #    await ctx.send(f"Your bot: " + str(hivebot.ip) + ":" + str(hivebot.port), ephemeral=True)  

        await self.client.draw(ctx=ctx, prompt=prompt, seed=seed, quantity=quantity, negative_prompt=negative_prompt,
            host=str(hivebot.url))     

    @interactions.extension_command(
            name="register",
            description="Registers an client machine running SD webui to Elrond's hivemind",
            scope=844680085298610177,
            options = [
                interactions.Option(
                    name="url",
                    description="Gradio App URL of the client machine",
                    type=interactions.OptionType.STRING,
                    min_length=30,
                    max_length=40, # 1024 In theory, but we string all fields together later so dont overdo it
                    required=True,
                ),
                interactions.Option(
                    name="username",
                    description="Gradio username",
                    type=interactions.OptionType.STRING,
                    required=False,
                ),
                interactions.Option(
                    name="password",
                    description="Gradio password",
                    type=interactions.OptionType.STRING,
                    required=False,
                ),
                interactions.Option(
                    name="nickname",
                    description="nickname for that sd-webui service",
                    type=interactions.OptionType.STRING,
                    min_length=0,
                    max_length=30,
                    required=False,
                ),
            ],
        )
    async def register(self, ctx: interactions.CommandContext, url: str, username: str = None, 
        password: str = None, nickname: str = None):
        access_token = None
        
        await ctx.send(f"Checking...", ephemeral=True)

        if username != None and password != None:
            access_token = await self.gradio_login(url, username, password)

        try:
            await self.test_gradio_url(url, access_token)
        except VersionNotSupportedError as err:
            await ctx.send(f"That client URL is running SD Web UI version " + err.foundver +
                " but we only support version 3.4/3.5", ephemeral=True)
            return
        except NoSdWebUiError:
            await ctx.send(f"That client URL is not running SD Web UI or there was a problem" +
                "connecting to it", ephemeral=True)
            return

        self.hivebots.append(HiveBot(url, access_token, nickname))

        if nickname != None:
            await ctx.send(f"client URLP added to hivemind with nickname " + nickname, ephemeral=True)
        else:
            await ctx.send(f"client URL added to hivemind", ephemeral=True)

    async def gradio_login(self, url: str, username: str, password: str):
        r = requests.post(url + "/login", data={'username': username, 'password': password}, allow_redirects=False)
        return r.cookies.get("access-token")

    # Using urllib here is a little limiting because it requires the user to include the URL scheme, 
    # otherwise the url is not recognized as valid.
    async def test_gradio_url(self, url: str, access_token: str = None):
        try:
            parsed = urlparse(url)
            
            if parsed.hostname[-11:] != ".gradio.app":
                raise URLError

            if access_token != None:
                resp = requests.get(url + "/config", timeout=2, cookies={"access-token": access_token}).json()
            else:
                resp = requests.get(url + "/config", timeout=2).json()
        except HTTPError:
            raise NoSdWebUiError
        except URLError:
            raise NoSdWebUIError
        
        if resp["version"] not in ["3.5\n", "3.4b3\n"]:
            raise VersionNotSupportedError(resp["version"])

def setup(client):
    Hive(client)
