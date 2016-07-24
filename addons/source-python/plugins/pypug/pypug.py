from messages import SayText2

def load():
    SayText2('PyPUG Loaded.').send()

def unload():
    SayText2('PyPUG Unloaded.').send()
