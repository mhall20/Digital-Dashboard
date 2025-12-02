# Digital-Dashboard

A digital dashboard for a standard car using a Python interface with an Arduino + CAN BUS module

## Table of Contents
- [Motivation](#motivation)
- [Project Overview](#overview)
- [Features](#features)
- [Getting Started](#how-to-get-started)
- [Usage](#usage)

## Motivation For Making This Project
- I've always worked on cars and wanted to use my coding skills for something related to the field
- Wanted to better understand CAN communication
- Wanted more embedded projects and specifically using different languages

## Project Overview
This project takes the statistics from your car's communication system and creates a digital dashboard to display them on your laptop.

This is the project I created as a first step to creating a physical gauge display.

## Features
- CAN communication: reads real time data from vehicle sensors using the Arduino and CAN module
- Python frontend: flexible display using pygame - easy for loopability and customizability

## Getting Started
Prerequisites:
  - Arduino MEGA
  - Arduino MEGA CAN-bus module
  - DB9 to OBD2 cord
  - Laptop for mobility

# Usage
For actual statistics, make sure Arduino and CAN are plugged in (if they aren't you can still run it in test mode)
- python dashboard.py
