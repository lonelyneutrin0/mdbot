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
from sim_src import *
import ovito
from dotenv import dotenv_values
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values
import ffmpeg

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
