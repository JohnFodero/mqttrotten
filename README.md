# MQTTrotten

Have an [Ikea Trotten](https://www.ikea.com/us/en/p/trotten-underframe-sit-stand-f-table-top-white-40507342/?utm_source=google&utm_medium=surfaces&utm_campaign=shopping_feed&utm_content=free_google_shopping_clicks_Workspaces&gad_source=1&gclid=Cj0KCQiA-62tBhDSARIsAO7twbYLZkYTWtj0h5qhJOKA5MM_DJlYNf3aIRdSqUBhJB-cnT_so4ZeZ8IaAiUGEALw_wcB) desk and an old drill and wish it was motorized? I do. 

MQTTrotten is a simple micropython + ESP32 project I created to achieve the following:
- Motorize a manual/crank standing desk, using a position-based control system so my preferred sitting and standing heights can be set. 
- Use MQTT to control the desk so I can integrate it with Home Bridge (or Home Assistant, or whatever smarthome platform you use). 
- Find a use for an old Dewalt 18v drill that no longer has functional batteries. Is a drill the ideal choice here? Debatable. But its in the name of reuse. 


## Table of Contents

- [Materials](#materials)
- [Installation](#installation)
- [Assembly](#assembly)
- [Usage](#usage)
- [Contributing](#contributing)

## Materials

- [Ikea Trotten](https://www.ikea.com/us/en/p/trotten-underframe-sit-stand-f-table-top-white-40507342/?utm_source=google&utm_medium=surfaces&utm_campaign=shopping_feed&utm_content=free_google_shopping_clicks_Workspaces&gad_source=1&gclid=Cj0KCQiA-62tBhDSARIsAO7twbYLZkYTWtj0h5qhJOKA5MM_DJlYNf3aIRdSqUBhJB-cnT_so4ZeZ8IaAiUGEALw_wcB) desk frame
- [ESP32](https://www.amazon.com/gp/product/B07Q576VWZ/ref=ppx_yo_dt_b_asin_title_o00_s00?ie=UTF8&psc=1)
- [ESP32 Motor Driver](https://www.amazon.com/gp/product/B07Q576VWZ/ref=ppx_yo_dt_b_asin_title_o00_s00?ie=UTF8&psc=1)
- A drill or high-torque geared motor of choice
- 12v, 20A power supply with some 12GA wire and a power switch
- 3D printed parts (STLs included in this repo)
- GT2 Belts
- Bearings
- Screws (M3 x ~12mm)
- A 5v buck converter
- Perf board, headers, connectors, solder, wire, pushbuttons, etc.
- A 3D printer (or a friend with one)
- A3144 Hall effect sensor (or similar) and a magnet 
- A drive shaft. I used an old drill bit ground down to size (its just smaller than the 1/4" hex drive on a drill). The included Trotten shaft could also be modified, but I wanted to keep it intact in case I ever wanted to go back to the manual crank.


## Installation

1. Clone this repo
2. Set up VSCode for Micropython development: 
    
    2.1 Setup tasks for vscode. Put the following in the .code-workspace:
    ```json
        "tasks": {
            "version": "2.0.0",
            "tasks": [
                {
                    "label": "ls",
                    "type": "shell",
                    "command": "uv run ampy ls"
                },
                {
                    "label": "run file",
                    "type": "shell",
                    "command": "uv run ampy run ${file}",
                    "problemMatcher": [],
                    "group": {
                        "kind": "build",
                        "isDefault": true
                    }
                },
                {
                    "label": "push project",
                    "type": "shell",
                    "command": "uv run ampy put ${workspaceFolder}/src/",
                }
            ]
        }
    ```
    This will allow for the standard "build" keybinding to run the current file on the board (in my case cmd+shift+B). Additionally, it adds a task to show any current files on the board, and one to push all files.  

    2.2 Configure the .ampy file. This will point ampy to use the correct serial port and baud rate. I include AMPY_DELAY in the config, but I havent noticed a difference in performance when adding a delay. 


2. Install `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. Install Micropython on your board. I'll leave it to the [uPython docs](https://micropython.org/download/) to explain this.
4. Test serial connection: `Tasks -> Run Task -> ampy ls`
5. Update the settings file and push the project to the board: `Tasks -> Run Task -> push project`
6. Print all 3d files in the `stl` directory.
7. Assemble! See below for assembly instructions.

## Assembly
TODO: Add pictures

## Usage

### Pushbuttons
Simply push the up or down button to raise or lower the desk. The desk will stop moving when the button is released. Pressing both buttons will set the current location as the bottom-most position.

### MQTT
The desk can be controlled via MQTT. The following topics are published/subscribed to:
- {base_topic}/position/set: Set the desk to a specific height. Payload should be an integer between 0 and `MAX_POS`.
- {base_topic}/position/get: Get the current position of the desk.
- {base_topic}/settings/set: Set the current settings of the desk. Payload format (a subset of the settings.json file):
	```json
	
	```
	Note that some settings will not take effect until the desk is restarted.
- {base_topic}/settings/get: Get the current settings of the desk.

## Retro

1. I avoided gears at first due to the higher friction and noise, but GT2 belts were simply the wrong choice here. The amount of tension needed to keep the belt from skipping is extremely great. If these end up breaking over time, I'll look into reworking this to use gears, or a belt with larger teeth. 

2. This uses a lot of power when lifting. I was shocked by how much current this draws. When testing at 20v, I pulled over 10A at medium-speeds. This is manageable by the motor, most drill batteries are rated to output well over 200W, and I greatly oversized the motor driver to make sure I had no issues with this (it also is readily available on Amazon/eBay/Aliexpress), but just something to be aware of. 

3. I use a file read/write to store the position in case of power loss. This isn't a perfect solution, and relies on manually setting the position on startup. Perhaps I'll add a homing sequence in the future.

## Contributing

Contributions to MQTTrotten are welcome! If you would like to contribute, please open an issue or pull request.
