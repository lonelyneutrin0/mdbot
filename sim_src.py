from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
import os
import numpy as np
import subprocess
import typing
import functools
import asyncio
from string import Template
import ovito
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
        data_initial = pipeline.compute(1)
        energies = np.array(data_initial.particles["c_ke"][...])
        pipeline.modifiers.append(ovito.modifiers.ColorCodingModifier(
          property = 'c_ke',
          gradient = ovito.modifiers.ColorCodingModifier.Magma(),
          start_value = 1.5,
          end_value = 2.2799e-5
        ))
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
        subprocess.call(["lmp", "-in", "pour.in", "-log", "none", "-var", "dump_file", f"{output_file_name}.dump"])
        subprocess.call(["gzip", "-f", f"{output_file_name}.dump"])
        os.chdir("../..")

        # should be calling LAMMPS here, just use preset simulations for now

        return Path(f"simulations/pour/{output_file_name}.dump.gz")
        
    @staticmethod
    def change_radius(frame: int, data: ovito.data.DataCollection) -> None:
        if(data.particles_.count == 0): return
        radius: float = 0.5
        types = data.particles_.particle_types_
        types.type_by_id_(1).radius = radius
        
    def render(self, path: Path, renderer: ovito.nonpublic.SceneRenderer) -> Path:

        pipeline = ovito.io.import_file(path)
        pipeline.modifiers.append(self.change_radius)
        pipeline.add_to_scene()

        viewport = ovito.vis.Viewport(
            type=ovito.vis.Viewport.Type.Right,
            camera_pos=(0, 0, 7.75),
            camera_dir = (-1, 0, 0),  # Direction the camera is looking
            camera_up = (0, 0, 1),
            fov=9.075
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