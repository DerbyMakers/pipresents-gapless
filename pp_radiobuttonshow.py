from pp_medialist import MediaList
from pp_show import Show
from pp_pathmanager import PathManager
from pp_utils import Monitor


class RadioButtonShow(Show):
    """
        starts at 'first-track' which can be any type of track or a show
        The show has links of the form 'symbolic-name play track-ref'
        An event with the symbolic-name will play the referenced track,
        at the end of that track control will return to first-track
        links in the tracks are ignored. Links are inherited from the show.
        timeout returns to first-track

        interface:
        * __init__ - initlialises the show
         * play - selects the first track to play (first-track) 
         * input_pressed,  - receives user events passes them to a Shower/Player if a track is playing,
                otherwise actions them depending on the symbolic name supplied
        * managed_stop  - stops the show from another show
        * terminate  - aborts the show, used whan clsing or after errors
        * track_ready_callback - called by the next track to be played to remove the previous track from display
        * subshow_ready_callback - called by the subshow to get the last track of the parent show
        * subshow_ended_callback - called at the start of a parent show to get the last track of the subshow
        
    """
    def __init__(self,
                 show_id,
                 show_params,
                 root,
                 canvas,
                 showlist,
                 pp_dir,
                 pp_home,
                 pp_profile):
        
        """
            show_id - index of the top level show caling this (for debug only)
            show_params - dictionary section for the menu
            canvas - the canvas that the menu is to be written on
            showlist  - the showlist
            pp_dir - Pi Presents directory
            pp_home - Pi presents data_home directory
            pp_profile - Pi presents profile directory
        """

        # init the common bits
        Show.base__init__(self,
                          show_id,
                          show_params,
                          root,
                          canvas,
                          showlist,
                          pp_dir,
                          pp_home,
                          pp_profile)
        

        # remove comment to turn the trace on          
        # self.trace=True

        # control debugging log
        self.mon.on()

        # create an instance of PathManager -  only used to parse the links.
        self.path = PathManager()
        
        # init variables
        self.track_timeout_timer=None
        self.show_timeout_timer=None
        self.next_track_signal=False
        self.current_track_ref=''


    def play(self,end_callback,show_ready_callback,direction_command,level):
        """ starts the hyperlink show at start-track 
              end_callback - function to be called when the show exits
              show_ready_callback - callback to get the previous track
              level is 0 when the show is top level (run from [start] or from show control)
              direction_command  - not used other than it being passed to a show
        """
        # need to instantiate the medialist here as in gapshow done in derived class
        self.medialist=MediaList()
        
        Show.base_play(self,end_callback,show_ready_callback, direction_command,level)
        
        if self.trace: print '\n\nRADIOBUTTONSHOW/play ',self.show_params['show-ref']
        
        # read the show links. Track links will NOT be added by ready_callback
        links_text=self.show_params['links']
        reason,message,self.links=self.path.parse_links(links_text)
        if reason == 'error':
            self.mon.err(self,message + " in show")
            self.end('error',message)
      
        # get the previous player and show from calling show
        Show.base_get_previous_player_from_parent(self)
        
        # and delete eggtimer
        if self.previous_shower is not  None:
            self.previous_shower.delete_eggtimer()
            
        self.do_first_track()

# ********************************
# Respond to external events
# ********************************

    # stop received from another concurrent show
    def managed_stop(self):
        self.stop_timers()
        Show.base_managed_stop(self)

    #  show timeout happened
    def show_timeout_stop(self):
        self.stop_timers()
        Show.base_show_timeout_stop(self)

    # terminate Pi Presents
    def terminate(self,reason):
        self.stop_timers()
        Show.base_terminate(self,reason)


   # respond to inputs
    def input_pressed(self,symbol,edge,source):

        self.mon.log(self,"received symbol: " + symbol)

        # does the symbol match a link, if so execute it
        if self.try_link(symbol,edge,source) is True:
            return

        # controls are disabled so ignore inputs
        if self.show_params['disable-controls'] == 'yes':
            return

        # does it match a control       
        # if at top convert symbolic name to operation otherwise lower down we have received an operatio    
        # look through list of controls to find match
        if self.level == 0:
            operation=Show.base_lookup_control(self,symbol,self.controls_list)
        else:
            operation=symbol
        # print 'operation',operation 
        if operation != '':
            self.do_operation(operation,edge,source)


    def do_operation(self,operation,edge,source):
        if self.shower  is not   None:
            # if next lower show is running pass down to stop the show and lower level
            self.shower.input_pressed(operation,edge,source)
        else:
            # control this show and its tracks
            if self.trace: print 'radiobuttonshow/input_pressed ',operation
            
            # service the standard inputs for this show
            # ??????? should stop from first_track ref get out of the show
            if operation == 'stop':
                self.stop_timers()
                if self.current_player is not None:
                    if self.current_track_ref == self.first_track_ref and self.level != 0:
                        self.user_stop_signal=True
                    self.current_player.input_pressed('stop')

            elif operation == 'pause':
                if self.current_player is not None:
                    self.current_player.input_pressed(operation)

                
            elif operation[0:4]=='omx-' or operation[0:6]=='mplay-'or operation[0:5] == 'uzbl-':
                if self.current_player is not None:
                    self.current_player.input_pressed(operation)


              
    def try_link(self,symbol,edge,source):
        # we have links which locally define symbolic names to be converted to radiobuttonshow operations
        # find the first entry in links that matches the symbol and execute its operation
        # print 'radiobuttonshow ',symbol
        found,link_op,link_arg=self.path.find_link(symbol,self.links)                    
        if link_op == 'play':
            self.do_play(link_arg,edge,source)
        return found



# *********************
# INTERNAL FUNCTIONS
# ********************

# *********************
# Show Sequencer
# *********************

    def track_timeout_callback(self):
        self.do_play(self.first_track_ref,'front','timeout')


    def do_play(self,track_ref,edge,source):
        if track_ref != self.current_track_ref:
            print 'executing play ',track_ref
            # cancel the show timeout when playing another track
            if self.show_timeout_timer is not None:
                self.canvas.after_cancel(self.show_timeout_timer)
                self.show_timeout_timer=None
            self.next_track_signal=True
            self.next_track_op='play'
            self.next_track_arg=track_ref
            if self.shower is not None:
                self.shower.input_pressed('stop',edge,source)
            elif self.current_player is not None:
                self.current_player.input_pressed('stop')
            else:
                self.what_next_after_showing()



    def do_first_track(self):
        # get first-track from profile
        self.first_track_ref=self.show_params['first-track-ref']

        # find the track-ref in the medialisst
        index = self.medialist.index_of_track(self.first_track_ref)
        if index >=0:
            # don't use select the track as not using selected_track in radiobuttonshow
            self.current_track_ref=self.first_track_ref
            # start the show timer when displaying the first track
            if self.show_timeout_timer is not None:
                self.canvas.after_cancel(self.show_timeout_timer)
                self.show_timeout_timer=None
            if int(self.show_params['show-timeout']) != 0:
                self.show_timeout_timer=self.canvas.after(int(self.show_params['show-timeout'])*1000 ,self.show_timeout_stop)

            # and load it
            self.start_load_show_loop(self.medialist.track(index))
        else:
            self.mon.err(self,"first-track not found in medialist: "+ self.show_params['first-track-ref'])
            self.end('error',"first track not found in medialist")


# *********************
# Playing show or track
# *********************

    def start_load_show_loop(self,selected_track):
        # shuffle players
        Show.base_shuffle(self)

        if self.trace: print 'radiobuttonshow/start_load_show_loop'
        
        self.display_eggtimer(Show.base_resource(self,'radiobuttonshow','m01'))

        if self.track_timeout_timer is not None:
            self.canvas.after_cancel(self.track_timeout_timer)
            self.track_timeout_timer=None

        # start timeout for the track if required           
        if self.current_track_ref != self.first_track_ref and int(self.show_params['track-timeout']) != 0:
            self.track_timeout_timer=self.canvas.after(int(self.show_params['track-timeout'])*1000,self.track_timeout_callback)
            
        # load the track or show
        # params - track,, track loaded callback, end eshoer callback,enable_menu
        Show.base_load_track_or_show(self,selected_track,self.what_next_after_load,self.end_shower,False)


   # track has loaded so show it.
    def what_next_after_load(self,status,message):
        if self.trace: print 'radiobuttonshow/what_next_after_load - load complete with status: ',status,'  message: ',message
        if self.current_player.play_state == 'load_failed':
            self.mon.err(self,'load failed')
            self.terminate_signal=True
            self.what_next_after_showing()
        else:
            if self.show_timeout_signal is True  or self.terminate_signal is True or self.stop_command_signal is True or self.user_stop_signal is True:
                self.what_next_after_showing()
            else:
                if self.trace: print 'menushow/what_next_after_load- showing track'
                self.current_player.show(self.track_ready_callback,self.finished_showing,self.closed_after_showing)


    

    def finished_showing(self,reason,message):
        # showing has finished with 'pause at end', showing the next track will close it after next has started showing
        if self.trace: print 'radiobuttonshow/finished_showing - pause at end'
        self.mon.log(self,"pause at end of showing track with reason: "+reason+ ' and message: '+ message)
        self.what_next_after_showing()

    def closed_after_showing(self,reason,message):
        # showing has finished with closing of player but track instance is alive for hiding the x_content
        if self.trace: print 'radiobuttonshow/closed_after_showing - closed after showing'
        self.mon.log(self,"Closed after showing track with reason: "+reason+ ' and message: '+ message)
        self.what_next_after_showing()


    # subshow or child show has ended
    def end_shower(self,show_id,reason,message):
        self.mon.log(self,self.show_params['show-ref']+ ' '+ str(self.show_id)+ ': Returned from shower with ' + reason +' ' + message)
        Show.base_end_shower(self)
        self.what_next_after_showing()

           

    def what_next_after_showing(self):
        if self.trace: print 'radiobuttonshow/what_next_after_showing '

        # need to terminate
        if self.terminate_signal is True:
            self.terminate_signal=False
            # what to do when closed or unloaded
            self.ending_reason='terminate'
            Show.base_close_or_unload(self)

        # show timeout
        elif self.show_timeout_signal is True:
            self.show_timeout_signal=False
            # what to do when closed or unloaded
            self.ending_reason='show-timeout'
            Show.base_close_or_unload(self)

        # used by managed_stop for stopping show from other shows. 
        elif self.stop_command_signal is True:
            self.stop_command_signal=False
            self.ending_reason='stop-command'
            Show.base_close_or_unload(self)

        # user wants to stop
        elif self.user_stop_signal is True:
            self.user_stop_signal=False
            self.ending_reason='user-stop'
            Show.base_close_or_unload(self)

        # user has selected another track
        elif self.next_track_signal is True:
            self.next_track_signal=False
            self.current_track_ref=self.next_track_arg                         
            index = self.medialist.index_of_track(self.current_track_ref)
            if index >=0:
                # don't use select the track as not using selected_track in radiobuttonshow
                # and load it
                self.start_load_show_loop(self.medialist.track(index))
            else:
                self.mon.err(self,"next track not found in medialist: "+ self.current_track_ref)
                self.end('error',"next track not found in medialist")
                    
        else:
            # track ends naturally or is quit so go back to first track
            self.do_first_track()


# *********************
# Interface with other shows/players to reduce black gaps
# *********************

    # called just before a track is shown to remove the  previous track from the screen
    # and if necessary close it
    def track_ready_callback(self):
        self.delete_eggtimer()
        Show.base_track_ready_callback(self)

    # callback from begining of a subshow, provide previous shower player to called show        
    def subshow_ready_callback(self):
        return Show.base_subshow_ready_callback(self)



    # called by end_shower of a parent show  to get the last track of the subshow
    def subshow_ended_callback(self):
        return Show.base_subshow_ended_callback(self)

    
# *********************
# End the show
# *********************
    def end(self,reason,message):
        self.stop_timers()
        Show.base_end(self,reason,message)


    def stop_timers(self):
        if self.show_timeout_timer is not None:
            self.canvas.after_cancel(self.show_timeout_timer)
            self.show_timeout_timer=None   
        if self.track_timeout_timer is not None:
            self.canvas.after_cancel(self.track_timeout_timer)
            self.track_timeout_timer=None  
           




