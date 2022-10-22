import ipaddress
from ipaddress import IPv4Address
import requests
import interactions
import datetime
import random

# custom Exception classes for more fine-grained error handlung
class VersionNotSupportedError(Exception):
    pass

class NoSdWebUiError(Exception):
    def __init__(self, foundver):
        self.foundver = foundver

# object representing individual bot instances (client machines)
class HiveBot():
    def __init__(self, ip: IPv4Address, port: int = 7860, nickname: str = None):
        self.ip = ip
        self.port = port
        self.nickname = nickname
        self.dt_added = datetime.datetime.now()

# extensino class
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
            host="http://" + str(hivebot.ip) + ":" + str(hivebot.port))     

    @interactions.extension_command(
            name="register",
            description="Registers an IP address to Elrond's hivemind",
            scope=844680085298610177,
            options = [
                interactions.Option(
                    name="ip",
                    description="IP address of the target machine",
                    type=interactions.OptionType.STRING,
                    min_length=7,
                    max_length=15, # 1024 In theory, but we string all fields together later so dont overdo it
                    required=True,
                ),
                interactions.Option(
                    name="port",
                    description="port of the target machine exposing sd-webui",
                    type=interactions.OptionType.INTEGER,
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
    async def register(self, ctx: interactions.CommandContext, ip: str = "", port: int = 7860, nickname: str = None):
        ipaddr = None
        try:
            ipaddr = ipaddress.ip_address(ip)
        except ValueError:
            await ctx.send(f"Sorry, that's not a valid IP v4 address", ephemeral=True)
            return

        try:
            await self.test_ip(ipaddr, port)
        except VersionNotSupportedError as err:
            await ctx.send(f"That IP is running SD Web UI version " + err.foundver +
                " but we only support version 3.4/3.5", ephemeral=True)
            return
        except NoSdWebUiError:
            await ctx.send(f"That IP is not running SD Web UI or there was a problem" +
                "connecting to it", ephemeral=True)
            return

        self.hivebots.append(HiveBot(ipaddr, port, nickname))

        if nickname is not None:
            await ctx.send(f"IP added to hivemind with nickname " + nickname, ephemeral=True)
        else:
            await ctx.send(f"IP added to hivemind", ephemeral=True)

    async def test_ip(self, ip: IPv4Address, port: int = 7860):
        try:
            resp = requests.get("http://" + str(ip) + ":" + str(port) + "/config", timeout=2).json()
        except HTTPError:
            raise NoSdWebUiError
        
        if resp["version"] not in ["3.5\n", "3.4b3\n"]:
            raise VersionNotSupportedError(resp["version"])
        else:
            return resp["version"].strip()

def setup(client):
    Hive(client)