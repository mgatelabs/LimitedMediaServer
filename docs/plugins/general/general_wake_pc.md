# Wake Up PC

**Action ID:** `action.wake.pc`
**Plugin class:** `WakeUpPcPlugin`
**Type:** General
**Feature flag:** Admin
**Requires config:** `PLUGIN.WAKE.MAC.ADDRESS`

## Description

Sends a Wake-on-LAN (WoL) magic packet to a remote PC on the local network to power it on.

## Arguments

- **PC** (`wake_pc_id`): Selectable PC to wake, or `*` to wake all configured PCs.

## What It Does

1. Reads the list of configured PCs from `PLUGIN.WAKE.MAC.ADDRESS` in server config. The value is a
   semicolon separated list of `NAME@MAC_ADDRESS` entries (e.g. `Office@AA:BB:CC:DD:EE:FF;Guest@11:22:33:44:55:66`).
   A bare MAC address is also allowed and defaults to itself as the display name.
2. Based on the selected PC argument (or `*` for all), sends a WoL magic packet to each target MAC address
   via `send_magic_packet()`.

The target machine must have Wake-on-LAN enabled in its BIOS/UEFI and network adapter settings.
