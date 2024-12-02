# Plugin Guide

## General

Plugins come in two parts, the Plugin and Task.  Plugins are what the user sees from the interface, they specify the arguments, and prevent tasks from being executed if there is a problem.  Tasks are the outcome of a plugin, it is a bit of code that will execute and can be monitored inside the app.

## What is a plugin?

Plugins are a way to create back-end processing tasks on demand.

Tasks are the result of executing a plugin.  A plugin can create none, one or multiple tasks.

Plugins have a life cycle, on server boot they are discovered, queried and determined if they are operational.  A plugin can define command line arguments or App Property arguments, that will be extracted on startup and the results can be accessed later.  App Properties are easier to maintain and should be used over command line arguments.

## What is a task?

A task is a class that is executed in the background.  It has a defined run method that will be called automatically.  It has access to the user that executed the task, and a series of logging and status methods.

### What is available to the plugin?


## How to make a plugin

### Part 1

Create your plugin file inside the ```./plugins``` folder.  There is no naming convention.

### Part 2

Define your plugin class inside, there is no naming convention.

Your class will need to extend on of the following base classes:
* ActionPlugin
  * General Plugin
* ActionBookPlugin
  * Plugin that executes in the content of a Book
  * Knows the path to book storage
* ActionMediaPlugin 
  * General Media Plugin
  * Knows the primary, alternative and temp media folders
* ActionMediaFolderPlugin
  * Plugin that executes in the context of a MediaFolder
  * Knows the primary, alternative and temp media folders
* ActionMediaFilePlugin
  * Plugin that executes in the context of a MediaFile
  * Knows the primary, alternative and temp media folders

```python
class HelloTask(ActionPlugin):
    def __init__(self):    
    super().__init__()
```

There are a few key methods that you need to override to successfully define a plugin.