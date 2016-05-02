
from myhdl import *
from random import random

@block
def weighted_random_reset_source(driven_reset, clock, 
                                 active_probability=0.5):
    '''A random reset source that has a couple of cycles of initialisation 
    first.
    '''
    @instance
    def custom_reset():
        driven_reset.next = 1
        yield(clock.posedge)
        driven_reset.next = 1
        yield(clock.posedge)
        while True:
            next_reset = random()
            # Be false when less than active_probability
            if next_reset > active_probability:
                driven_reset.next = 1
            else:
                driven_reset.next = 0
                
            yield(clock.posedge)

    return custom_reset
