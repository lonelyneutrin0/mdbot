from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
import os
import subprocess
import typing
import functools
import asyncio
from string import Template

import ovito
from dotenv import dotenv_values
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values
import ffmpeg


def to_thread(func: typing.Callable) -> typing.Coroutine:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper


class Scenario(Enum):

    TWO_PHASE_COPPER = 0
    POUR = 1
    SOMETHING_ELSE = 2


class AvailableRenderer(Enum):

    OPENGL = 0
    TACHYON = 1


@dataclass
class Simulation(ABC):

    @abstractmethod
    def get_description(self, values: dict) -> str:

        """
        run description
        """

        pass

    @abstractmethod
    @to_thread
    def run(self, temperature: float) -> Path:

        """
        runs and stores in a dump file, and returns the path of that dump file
        """

        pass

    @abstractmethod
    def render(self, path: Path, renderer: ovito.nonpublic.SceneRenderer) -> Path:

        """
        renders and returns the path holding the animation
        """

        pass


@dataclass
class TwoPhaseCopper(Simulation):

    def get_description(self, values: dict) -> str:

        with Path("simulations/copper/description.txt").open("r") as file:
            template = Template(file.read())

        return template.substitute(**values)
    
    @to_thread
    def run(self, temperature: float) -> Path:
        
        os.chdir("simulations/copper")
        subprocess.call(["lmp", "-in", "copper.in", "-var", "temperature", f"{temperature:.0f}", "-log", "none"])
        subprocess.call(["gzip", "-f", f"equil_{temperature:.0f}.dump"])
        os.chdir("../..")

        # should be calling LAMMPS here, just use preset simulations for now

        return Path(f"simulations/copper/equil_{temperature:.0f}.dump.gz")
    
    def render(self, path: Path, renderer: ovito.nonpublic.SceneRenderer) -> Path:

        pipeline = ovito.io.import_file(path)
        pipeline.add_to_scene()
    
        viewport = ovito.vis.Viewport(
            type=ovito.vis.Viewport.Type.Front,
            camera_pos=(-0.00376349, 0.00141782, 0.00535878),
            camera_dir=(0.0, 0.0, 1.0),
            camera_up=(1.0, 0.0, 0.0),
            fov=24.8456
        )

        # temp file name
        file_name = "animation.mp4"
    
        viewport.render_anim(
            filename=file_name,
            size=(640, 480),
            background=(49 / 255, 51 / 255, 56 / 255),
            renderer=renderer
        )
        
        # need to re-encode
        # thanks ChatGPT
        
        ffmpeg.input(file_name).output(
            f"copy_{file_name}",
            vcodec="libx264",     # Video codec: H.264
            acodec="aac",         # Audio codec: AAC
            audio_bitrate="192k", # Audio bitrate (optional)
            movflags="faststart"  # Optimize for web streaming
        ).run(overwrite_output=True)

        Path(file_name).unlink()

        return Path(f"copy_{file_name}")
    
@dataclass
class Pour(Simulation): 
    """
    Pouring of granular particles into a 3d box, then chute flow
    """
    def get_description(self, values: dict) -> str:
        with Path("simulations/pour/description.txt").open("r") as file:
            template = Template(file.read())

        return template.substitute(**values)
    
    @to_thread
    def run(self, temperature: float) -> Path:
        output_file_name = "pour_output"
        os.chdir("simulations/pour")
        subprocess.call(["lmp", "-in", "pour.in", "-log", "none"])
        subprocess.call(["gzip", "-f", f"{output_file_name}.dump"])
        os.chdir("../..")

        # should be calling LAMMPS here, just use preset simulations for now

        return Path(f"simulations/copper/{output_file_name}.dump.gz")
    
    def render(self, path: Path, renderer: ovito.nonpublic.SceneRenderer) -> Path:

        pipeline = ovito.io.import_file(path)
        pipeline.add_to_scene()

        viewport = ovito.vis.Viewport(
            type=ovito.vis.Viewport.Type.Front,
            camera_pos=(-0.00376349, 0.00141782, 0.00535878),
            camera_dir=(0.0, 0.0, 1.0),
            camera_up=(1.0, 0.0, 0.0),
            fov=24.8456
        )

        # temp file name
        file_name = "animation.mp4"

        viewport.render_anim(
            filename=file_name,
            size=(640, 480),
            background=(49 / 255, 51 / 255, 56 / 255),
            renderer=renderer
        )
        
        # need to re-encode
        # thanks ChatGPT
        
        ffmpeg.input(file_name).output(
            f"copy_{file_name}",
            vcodec="libx264",     # Video codec: H.264
            acodec="aac",         # Audio codec: AAC
            audio_bitrate="192k", # Audio bitrate (optional)
            movflags="faststart"  # Optimize for web streaming
        ).run(overwrite_output=True)

        Path(file_name).unlink()

        return Path(f"copy_{file_name}")

@dataclass
class SomethingElse(Simulation):

    def get_description(self, values: dict) -> str:

        raise NotImplementedError

    @to_thread
    def run(temperature: float) -> Path:

        raise NotImplementedError
    
    def render(path: Path, renderer: ovito.nonpublic.SceneRenderer) -> Path:

        raise NotImplementedError
    

MAPPING = {
    Scenario.TWO_PHASE_COPPER: TwoPhaseCopper(),
    Scenario.POUR: Pour(),
    Scenario.SOMETHING_ELSE: SomethingElse()
}

RENDERERS = {
    AvailableRenderer.OPENGL: ovito.vis.OpenGLRenderer(),
    AvailableRenderer.TACHYON: ovito.vis.TachyonRenderer()
}


def main():
    
    config = dotenv_values(".env")

    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix="!", intents=intents)
    guild = bot.get_guild(config["GUILD_ID"])
    
    @bot.event
    async def on_ready():

        await bot.tree.sync(guild=guild)

    @bot.tree.command(name="render", guild=guild)
    @app_commands.describe(
        scenario="Choice from available simulations",
        temperature="Temperature in Celsius",
        renderer="Renderer to choose. Tachyon has ambient occlusion"
    )
    @app_commands.choices(
        scenario=[app_commands.Choice(name=x.name, value=x.value) for x in Scenario],
        renderer=[
            app_commands.Choice(name="OpenGL (faster)", value=AvailableRenderer.OPENGL.value),
            app_commands.Choice(name="Tachyon (prettier)", value=AvailableRenderer.TACHYON.value)
        ]
    )
    async def render(
        interaction: discord.Interaction,
        scenario: Scenario,
        temperature: app_commands.Range[float, 700.0, 1800.0],
        renderer: AvailableRenderer
    ):

        temperature += 273.15
        channel = bot.get_channel(interaction.channel_id)

        simulation = MAPPING[scenario]
        await interaction.response.send_message(content="Running the simulation... Give me a bit of time :)")
        message = await interaction.original_response()
        dump_file_path = await simulation.run(temperature)
        await message.edit(content="Simulation ran successfully! Now I have to render it... Some more time please! :D")
        animation_path = simulation.render(dump_file_path, renderer=RENDERERS[renderer])

        file = discord.File(animation_path.name, filename=animation_path.name)
        description = simulation.get_description({"temperature": temperature})
        await channel.send(f"Your render is done <@{interaction.user.id}>! {description}", file=file)
        dump_file_path.unlink()
        animation_path.unlink()
        return
    
    @bot.tree.command(name="hello", guild=guild)
    async def hello(
        interaction: discord.Interaction
    ): 
        await interaction.response.send_message("Hello World")
    bot.run(config["API_KEY"])


if __name__ == "__main__":

    main()
