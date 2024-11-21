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
from discord.ui import Select, View
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values
import ffmpeg
import asyncio 

MAPPING = {
    Scenario.TWO_PHASE_COPPER: TwoPhaseCopper(),
    Scenario.POUR: Pour(),
    Scenario.SOMETHING_ELSE: SomethingElse()
}

RENDERERS = {
    AvailableRenderer.OPENGL: ovito.vis.OpenGLRenderer(),
    AvailableRenderer.TACHYON: ovito.vis.TachyonRenderer()
}

PARAMS = { 
    Scenario.TWO_PHASE_COPPER: [{"label": "Temperature", "placeholder": "Enter the temperature in Celsius [700-1800]."}],
    Scenario.POUR: [{"label": "Radius", "placeholder": "Enter the radius of the particles."}],
    Scenario.SOMETHING_ELSE: [{"label": "NULL", "placeholder": "NULL"}]
}
# class DropdownMenu(Select):
#     def __init__(self, labels: list, descriptions: list, user_input: asyncio.Future, emojis:list=None):

#         # asyncio.Future stores the input of the user 
#         if emojis is None:
#             options = [discord.SelectOption(label=labels[i], description=descriptions[i]) for i in range(len(labels))]
#         else: 
#             options = [discord.SelectOption(label=labels[i], description=descriptions[i], emoji=emojis[i]) for i in range(len(labels))]
#         # Initialize the Select menu
#         super().__init__(
#             placeholder="Choose an option...",
#             min_values=1,
#             max_values=1,
#             options=options,
#         )
#         self.user_input = user_input

#     async def callback(self, interaction: discord.Interaction):
#         # Handle when a user selects an option
#         self.user_input.set_result(self.values[0])

# Modal class
class Modal(discord.ui.Modal):
    def __init__(self, components: list[dict], future_responses: asyncio.Future):
        super().__init__(title="Simulation Query")

        # Dynamically create text input fields
        for component in components:
            input_field = discord.ui.TextInput(
                label=component.get("label"),
                placeholder=component.get("placeholder", "Enter the value here."),
                required=component.get("required", True),
            )
            self.add_item(input_field)
        self.future_responses = future_responses    

    async def on_submit(self, interaction: discord.Interaction):
        # Collect all responses from the modal
        responses = {item.label.lower(): (float) (item.value) for item in self.children if isinstance(item, discord.ui.TextInput)}
        self.future_responses.set_result(responses)
        await interaction.response.send_message("Your responses have been submitted!", ephemeral=True)


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
        renderer: AvailableRenderer
    ):
        param_responses = asyncio.Future()
        modal = Modal(components=PARAMS[scenario], future_responses=param_responses)
        await interaction.response.send_modal(modal)
        await param_responses    
        params = param_responses.result()
        params['temperature'] += 273.15
        channel = bot.get_channel(interaction.channel_id)
        simulation = MAPPING[scenario]
        message = await interaction.channel.send(content="Running the simulation... Give me a bit of time :)")
        dump_file_path = await simulation.run(**params)
        await message.edit(content="Simulation ran successfully! Now I have to render it... Some more time please! :D")
        animation_path = simulation.render(dump_file_path, renderer=RENDERERS[renderer])

        file = discord.File(animation_path.name, filename=animation_path.name)
        description = simulation.get_description({"temperature": param_responses.result()['temperature']})
        await channel.send(f"Your render is done <@{interaction.user.id}>! {description}", file=file)
        dump_file_path.unlink()
        animation_path.unlink()
        return
    
    @bot.tree.command(name="hello", guild=guild)
    async def hello(interaction): 
        fields = [
                {"label": "Your Name", "placeholder": "Enter your name"},
                {"label": "Favorite Color", "placeholder": "Enter your favorite color"},
                {"label": "Hobby", "placeholder": "Enter your hobby"},
            ]
        resps = asyncio.Future()
        modal = Modal(components=fields, future_responses=resps)
        await interaction.response.send_modal(modal)
        await resps
        await interaction.channel.send(resps.result())

    bot.run(config["API_KEY"])


if __name__ == "__main__":

    main()
