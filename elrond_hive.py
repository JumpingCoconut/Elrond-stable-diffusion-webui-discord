import datetime
import random
from urllib.error import URLError
from urllib.parse import urlparse

import interactions
import requests
from urllib3.exceptions import HTTPError


# custom Exception classes for more fine-grained error handling
class VersionNotSupportedError(Exception):
    pass


class NoSdWebUiError(Exception):
    def __init__(self, foundver) -> None:
        self.foundver = foundver


# object representing individual bot instances (client machines)
class HiveBot():
    def __init__(self, url: str, access_token: str = None, nickname: str = None,
                 config: dict = None) -> None:
        # URL pointing to the SD Web UI exposed by the machine, e. g. https://xxxxx.gradio.app
        self.url = url
        # access token for accessing the SD Web UI service using its own
        # session cookie-based login mechanism. May be None if the SD Web UI
        # instance isn't password protected
        self.access_token = access_token
        # nickname given to the client machine, used for identifying it,
        # e. g. when it uploads a picture it has drawn
        self.nickname = nickname
        # some important configuration parameters
        self.config = config
        # datetime of this machine's registration to the hivemind, primarily used for
        # time-based invalidation/deregistration
        self.dt_added = datetime.datetime.now()


# Discord interactions extension class
class Hive(interactions.Extension):
    bot: interactions.Client
    hivebots: list[HiveBot]

    def __init__(self, client) -> None:
        self.bot = client
        self.hivebots = []

    def get_random_client(self) -> HiveBot | None:
        try:
            return random.choice(self.hivebots)
        except:
            return None

    # all this command does is call the "main" draw_image method on
    # a random hivebot machine
    @interactions.extension_command(
        name="draw_hivemind",
        description="Makes someone else draw a picture for you!",
        scope=844680085298610177,
        options=[
            interactions.Option(
                    name="prompt",
                    description="Words that describe the image",
                    type=interactions.OptionType.STRING,
                    min_length=0,
                    max_length=400,  # 1024 In theory, but we string all
                # fields together later so dont overdo it
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
                max_length=400,  # 1024 In theory, but we string all
                                 # fields together later so dont overdo it
                required=False,
            ),
        ]
    )
    async def draw_hivemind(self, ctx: interactions.CommandContext, prompt: str = "",
                            seed: int = -1, quantity: int = 1,
                            negative_prompt: str = ""):
        # select a random machine from the hivemind or fail if there are none
        try:
            hivebot = random.choice(self.hivebots)
        except IndexError:
            await ctx.send("Unfortunately, there are no bots in the hivemind right now",
                           ephemeral=True)
            return
        # if hivebot.nickname is not None:
        #    await ctx.send("Your bot: " + str(hivebot.ip) + ":" + str(hivebot.port) +
        #        " as " + hivebot.nickname, ephemeral=True)
        # else:
        #    await ctx.send("Your bot: " + str(hivebot.ip) + ":" + str(hivebot.port),
        #                   ephemeral=True)

        await self.client.draw(ctx=ctx, prompt=prompt, seed=seed, quantity=quantity,
                               negative_prompt=negative_prompt, host=hivebot.url)

    @interactions.extension_command(
        name="register",
        description="Registers a client running SD webui to Elrond's hivemind",
        scope=844680085298610177,
        options=[
            interactions.Option(
                    name="url",
                    description="Gradio App URL of the client machine",
                    type=interactions.OptionType.STRING,
                    min_length=30,
                    max_length=40,  # 1024 In theory, but we string all
                                    # fields together later so dont overdo it
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
    async def register(self, ctx: interactions.CommandContext, url: str,
                       username: str = None, password: str = None,
                       nickname: str = None) -> None:
        access_token = None

        # avoid timeout
        await ctx.send("Checking...", ephemeral=True)

        # only try to obtain an access token if the user provides credentials
        if username is not None and password is not None:
            access_token = await self.gradio_login(url, username, password)

        try:
            await self.test_gradio_url(url, access_token)
        except VersionNotSupportedError as err:
            await ctx.send("That client URL is running SD Web UI version " +
                           err.foundver + " but we only support version 3.4/3.5",
                           ephemeral=True)
            return
        except NoSdWebUiError:
            await ctx.send("""That client URL is not running SD Web UI or there was
                           a problem connecting to it""", ephemeral=True)
            return

        botconfig = {}
        r = requests.get(url + "/config", timeout=2,
                         cookies={"access-token": access_token}).json()
        for component in r["components"]:
            if component["props"].get("label") == "Stop At last layers of CLIP model":
                botconfig["CLIP"] = component["props"].get("value")
            elif component["props"].get("label") == "Stable Diffusion checkpoint":
                botconfig["checkpoint"] = component["props"].get("value")

        self.hivebots.append(HiveBot(url, access_token, nickname, botconfig))

        if nickname is not None:
            await ctx.send("client URL added to hivemind with nickname " + nickname, ephemeral=True)
        else:
            await ctx.send("client URL added to hivemind", ephemeral=True)

    # attempt to login with the user-provided credentials and obtain an access token
    async def gradio_login(self, url: str, username: str, password: str) -> str | None:
        r = requests.post(
            url + "/login", data={"username": username, "password": password},
            allow_redirects=False)
        return r.cookies.get("access-token")

    # check whether the machine URL provided by the user looks like a valid SD Web UI
    async def test_gradio_url(self, url: str, access_token: str = None) -> None:
        try:
            # using urllib here is a little limiting because it requires the user
            # to include the URL scheme (https://), otherwise the url is not
            # recognized as valid.
            parsed = urlparse(url)

            # check whether the URL points to a subdomain under "gradio.app", these
            # are the only URLs Gradio's share mode will generate
            if parsed.hostname[-11:] != ".gradio.app":
                raise URLError

            if access_token is not None:
                resp = requests.get(url + "/config", timeout=2,
                                    cookies={"access-token": access_token}).json()
            else:
                resp = requests.get(url + "/config", timeout=2).json()
        except HTTPError:
            raise NoSdWebUiError
        except URLError:
            raise NoSdWebUiError

        # only allow versions we currently support
        if resp["version"] not in ["3.5\n", "3.4b3\n"]:
            raise VersionNotSupportedError(resp["version"])


def setup(client: interactions.Client) -> None:
    """The obligatory setup method.

    This method is required by the "interactions" package for creating a
    working Bot extension that can be loaded via interactions.Client.load().

    """
    Hive(client)
