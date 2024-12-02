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

# Dictionary to access the simulation, parameters and restrictions on them
MAPPING = {
    Scenario.TWO_PHASE_COPPER: TwoPhaseCopper(restrictions = {"temperature": (700, 1800)}),
    Scenario.POUR: Pour(),
    Scenario.SOMETHING_ELSE: SomethingElse()
}

RENDERERS = {
    AvailableRenderer.OPENGL: ovito.vis.OpenGLRenderer(),
    AvailableRenderer.TACHYON: ovito.vis.TachyonRenderer()
}

# Modal Data for creating the options
PARAMS = { 
    Scenario.TWO_PHASE_COPPER: [{"label": "Temperature", "placeholder": "Enter the temperature in Celsius [700-1800]."}],
    Scenario.POUR: [],
    Scenario.SOMETHING_ELSE: [{"label": "NULL", "placeholder": "NULL"}]
}

# Dropdown menu class if we ever need it
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
    def __init__(self, components: list[dict], future_responses: asyncio.Future, simulation: Scenario):
        """
        Parameters: 
        components: A list of dictionaries containing the modal options data
        future_responses: An asyncio.Future object to store the modal responses- required because the modal response is handled asynchronously 
        simulation: The type of simulation being run 
        """
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
        self.simulation = MAPPING[simulation] 
    
    async def on_submit(self, interaction: discord.Interaction):
        """
        The async function that handles modal responses 

        Parameters: 
        interaction: The discord.Interaction object (in this case, the modal itself) 
        """
        # Collect all responses from the modal
        responses = {item.label.lower(): (float) (item.value) for item in self.children if isinstance(item, discord.ui.TextInput)}  
        
        # Data Validation
        if len(self.simulation.restrictions) > 0: 
            for i in responses: 
                if not (self.simulation.restrictions[i][0] <= responses[i] <= self.simulation.restrictions[i][1]): 
                    return ValueError( await interaction.response.send_message(f"You entered an invalid value! Please enter a {i} value between {self.simulation.restrictions[i][0]} and {self.simulation.restrictions[i][1]}"))
        
        # Push the validated options to an asyncio object- handle in the main render function
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
        # params should default to an empty dict (for simulations that don't accept parameters)
        params = {}
        
        # Send a modal if the simulation takes parameters
        if len(PARAMS[scenario]) > 0:

            # Store the parameters in an asyncio.Future variable
            param_responses = asyncio.Future()
            modal = Modal(components=PARAMS[scenario], future_responses=param_responses, simulation = scenario)
            await interaction.response.send_modal(modal)
            await param_responses    
            params = param_responses.result()

            # Check the validity of the parameters
            if(params is None): return
        else: 
            message = await interaction.response.send_message(content="Querying....", ephemeral=True)

        # Convert temp to Kelvin for the TWO_PHASE_COPPER simulation || We can put other simulation-specific unit conversions here
        if scenario == Scenario.TWO_PHASE_COPPER: 
            params['temperature'] += 273.15
        
        channel = bot.get_channel(interaction.channel_id)
        simulation = MAPPING[scenario]
        message = await interaction.channel.send(content="Running the simulation... Give me a bit of time :)")

        # Run the simulation with the assigned parameters- note that this means the dictionary keys should correspond exactly to the variable names in the simulation run function
        dump_file_path = await simulation.run(**params)
        await message.edit(content="Simulation ran successfully! Now I have to render it... Some more time please! :D")
        animation_path = simulation.render(dump_file_path, renderer=RENDERERS[renderer])

        file = discord.File(animation_path.name, filename=animation_path.name)
        description = simulation.get_description(params)
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
