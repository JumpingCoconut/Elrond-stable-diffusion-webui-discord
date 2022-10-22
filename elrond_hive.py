import ipaddress
from ipaddress import IPv4Address
import requests
import interactions

class VersionNotSupportedError(Exception):
    pass

class NoSdWebUiError(Exception):
    def __init__(self, foundver):
        self.foundver = foundver

class Hive(interactions.Extension):
    def __init__(self, client):
        self.bot: interactions.Client = client

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
            ],
        )
    async def register(self, ctx: interactions.CommandContext, ip: str = "", port: int = 7860):
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

        await ctx.send(f"good IP", ephemeral=True)

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