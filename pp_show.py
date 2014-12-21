import os
from pp_resourcereader import ResourceReader
from pp_controlsmanager import ControlsManager
from pp_showmanager import ShowManager
from pp_timeofday import TimeOfDay
from pp_imageplayer import ImagePlayer
from pp_videoplayer import VideoPlayer
from pp_audioplayer import AudioPlayer
from pp_browserplayer import BrowserPlayer
from pp_messageplayer import MessagePlayer
from pp_menuplayer import MenuPlayer
from pp_utils import Monitor

class Show(object):


    # ******************************
    # init a show
    # ******************************

    def base__init__(self,
                     show_id,
                     show_params,
                     root,
                     canvas,
                     showlist,
                     pp_dir,
                     pp_home,
                     pp_profile,
                     command_callback):

        # instantiate arguments
        self.show_id=show_id
        self.show_params=show_params
        self.root=root
        self.show_canvas=canvas
        self.canvas=canvas['canvas-obj']
        self.show_canvas_x1 = canvas['show-canvas-x1']
        self.show_canvas_y1 = canvas['show-canvas-y1']
        self.show_canvas_x2 = canvas['show-canvas-x2']
        self.show_canvas_y2 = canvas['show-canvas-y2']
        self.show_canvas_width = canvas['show-canvas-width']
        self.show_canvas_height= canvas['show-canvas-height']
        self.show_canvas_centre_x= canvas['show-canvas-centre-x']
        self.show_canvas_centre_y= canvas['show-canvas-centre-y']
        self.showlist=showlist
        self.pp_dir=pp_dir
        self.pp_home=pp_home
        self.pp_profile=pp_profile
        self.command_callback=command_callback

        # init things that will then be reinitialised by derived classes
        self.medialist=None

        # set up logging 
        self.mon=Monitor()

        # trace is off by default
        self.trace=False      

        # open resources
        self.rr=ResourceReader()

        # create and instance of TimeOfDay scheduler so we can add events
        self.tod=TimeOfDay()
        
        # create an  instance of showmanager so we can init child/subshows
        self.show_manager=ShowManager(self.show_id,self.showlist,self.show_params,self.root,self.show_canvas,self.pp_dir,self.pp_profile,self.pp_home)

        # init variables
        self.current_player=None
        self.previous_player=None
        self.shower=None
        self.previous_shower=None
        self.user_stop_signal= False
        self.exit_signal=False
        self.terminate_signal=False
        self.show_timeout_signal=False
        self.egg_timer=None
        self.admin_message=None
        self.ending_reason=''


    def base_play(self,end_callback,show_ready_callback, direction_command,level,controls_list):

        """ starts the common parts of the show
              end_callback - function to be called when the show exits- callback gets last player of subshow
              show_ready_callback - callback at start to get previous_player
              top is True when the show is top level (run from [start] or by show command from another show)
              direction_command - 'forward' or 'backward' direction to play a subshow (default 'nil')
        """
        # instantiate the arguments
        self.end_callback=end_callback
        self.show_ready_callback=show_ready_callback
        self.direction_command=direction_command
        self.level=level
        self.controls_list=controls_list
        if self.trace: print 'show/play',self.show_params['show-ref'],' at level ',self.level
        self.mon.log(self,self.show_params['show-ref']+ ' '+ str(self.show_id)+ ": Starting show")

        # check  data files are available.
        self.medialst_file = self.pp_profile + "/" + self.show_params['medialist']
        if not os.path.exists(self.medialst_file):
            self.mon.err(self,"Medialist file not found: "+ self.medialst_file)
            self.end('error',"Medialist file not found")

        # read the medialist for the show
        if self.medialist.open_list(self.medialst_file,self.showlist.sissue()) is False:
            self.mon.err(self,"Version of medialist different to Pi Presents")
            self.end('error',"Version of medialist different to Pi Presents")

        # get control bindings for this show if top level
        controlsmanager=ControlsManager()
        if self.level == 0:
            if self.show_params['disable-controls'] == 'yes':
                self.controls_list=[]
            else:
                self.controls_list=controlsmanager.default_controls()
                # and merge in controls from profile
                self.controls_list=controlsmanager.merge_show_controls(self.controls_list,self.show_params['controls'])
            

    def base_get_previous_player_from_parent(self):
        if self.show_ready_callback is not None:
            # get the previous player from calling show its stored in current because its going to be shuffled before use
            self.previous_shower, self.current_player=self.show_ready_callback()
            if self.trace: print 'show/ start of show, previous shower and player is',self.previous_shower,self.current_player

    # dummy, must be overidden by derived class
    def subshow_ready_callback(self):
        self.mon.err(self,"subshow_ready_callback not overidden")
        # set what to do when closed or unloaded
        self.ending_reason='killed'
        Show.base_close_or_unload(self)


    def base_subshow_ready_callback(self):
        # callback from begining of a subshow, provide previous player to called show
        # used by show_ready_callback of called show
        # in the case of a menushow last track is always the menu
        if self.trace: print 'show/subshow_ready_callback sends ',self,self.previous_player
        return self,self.previous_player


    def base_shuffle(self):
        self.previous_player=self.current_player
        self.current_player = None
        if self.trace: print '\n\n\nshow/LOOP STARTS WITH current is', self.current_player
        if self.trace: print '                     previous is', self.previous_player



    def base_load_track_or_show(self,selected_track,loaded_callback,end_shower_callback,enable_menu):
        track_type=selected_track['type']
        if track_type == "show":
            # get the show from the showlist
            index = self.showlist.index_of_show(selected_track['sub-show'])
            if index <0:
                self.mon.err(self,"Show not found in showlist: "+ selected_track['sub-show'])
                self.end('error','show not in showlist')
            else:
                self.showlist.select(index)
                selected_show=self.showlist.selected_show()
                self.shower=self.show_manager.init_subshow(self.show_id,selected_show,self.show_canvas)
                if self.trace: print 'show/load_track_or_show - show is ',self.shower,selected_show['show-ref']
                if self.shower is None:
                    self.mon.err(self,"Unknown Show Type: "+ selected_show['type'])
                    self.terminate_signal=True
                    self.what_next_after_showing()
                else:
                    self.shower.play(end_shower_callback,self.subshow_ready_callback,self.direction_command,self.level+1,self.controls_list)
        else:
            # dispatch track by type
            self.mon.log(self,self.show_params['show-ref']+ ' '+ str(self.show_id)+ ": Track type is: "+ track_type)
            
            self.current_player=self.base_init_selected_player(selected_track)
            # messageplayer passes the text not a file name
            if selected_track['type'] == 'message':
                track_file=selected_track['text']
            else:
                track_file=self.base_complete_path(selected_track['location'])
            if self.trace: print 'show/load_track_or_show  - track is - ',track_file
            if self.trace: print 'show/load_track_or_show - current_player is',self.current_player   
            self.current_player.load(track_file,
                                     loaded_callback,
                                     enable_menu=enable_menu)



    # dummy, must be overidden by derived class
    def what_next_after_showing(self):
        self.mon.err(self,"what_next_after showing not overidden")
        # set what to do when closed or unloaded
        self.ending_reason='killed'
        Show.base_close_or_unload(self)


    def base_init_selected_player(self,selected_track):
        # dispatch track by type
        track_type=selected_track['type']
        self.mon.log(self,"Track type is: "+ track_type)
                                      
        if track_type == "image":
            return ImagePlayer(self.show_id,self.showlist,self.root,self.show_canvas,
                               self.show_params,selected_track,self.pp_dir,self.pp_home,
                               self.pp_profile,self.end,self.command_callback)
    
        elif track_type == "video":
            return VideoPlayer(self.show_id,self.showlist,self.root,self.show_canvas,
                               self.show_params,selected_track,self.pp_dir,self.pp_home,
                               self.pp_profile,self.end,self.command_callback)

        elif track_type == "audio":
            return AudioPlayer(self.show_id,self.showlist,self.root,self.show_canvas,
                               self.show_params,selected_track,self.pp_dir,self.pp_home,
                               self.pp_profile,self.end,self.command_callback)

        elif track_type == "web":
            return BrowserPlayer(self.show_id,self.showlist,self.root,self.show_canvas,
                                 self.show_params,selected_track,self.pp_dir,self.pp_home,
                                 self.pp_profile,self.end,self.command_callback)
  
        elif track_type == "message":
            return MessagePlayer(self.show_id,self.showlist,self.root,self.show_canvas,
                                 self.show_params,selected_track,self.pp_dir,self.pp_home,
                                 self.pp_profile,self.end,self.command_callback)

        elif track_type == "menu":
            return MenuPlayer(self.show_id,self.showlist,self.root,self.show_canvas,
                              self.show_params,selected_track,self.pp_dir,self.pp_home,
                              self.pp_profile,self.end,self.command_callback)
                                   
        else:
            return None


    # dummy, must be overidden by derived class
    def track_ready_callback(self):
        self.mon.err(self,"track_ready_callback not overidden")
        # set what to do when closed or unloaded
        self.ending_reason='killed'
        Show.base_close_or_unload(self)


    # called just before a track is shown to remove the  previous track from the screen
    # and if necessary close it        
    def base_track_ready_callback(self):            
        if self.trace: print 'show/track_ready_callback '
        # close the player from the previous track
        if self.previous_player is not  None:
            if self.trace: print 'show/hiding previous',self.previous_player
            self.previous_player.hide()
            if self.previous_player.get_play_state() == 'showing':
                # showing or frozen
                if self.trace: print 'show/closing previous',self.previous_player
                self.previous_player.close(self._base_closed_callback_previous)
            else:
                if self.trace: print 'show/previous is none\n'
                self.previous_player=None


    def _base_closed_callback_previous(self,status,message):
        if self.trace: print 'show/closed_callback previous is None  - was',self.previous_player
        self.previous_player=None


    # used by end_shower to get the last track of the subshow
    def base_end_shower(self):
        if self.trace: print 'show/end_shower returned back to level ',self.level
        # get the last track played from the subshow
        self.current_player=self.shower.subshow_ended_callback()
        self.previous_player=None
        if self.trace: print 'show/end_shower  - get previous_player from subshow *****',self.current_player
        self.shower=None


    # close or unload the current player when ending the show
    def base_close_or_unload(self):
        if self.trace: print 'show/base_close_or_unload ',self.current_player
        # need to test for None because player may be made None by subshow lower down the stack for terminate
        if self.current_player is not None:
            if self.trace: print 'show/base_close_or_unload ',self.current_player.get_play_state()
            if self.current_player.get_play_state() in ('loaded','showing','show-failed'):
                if self.current_player.get_play_state() == 'loaded':
                    if self.trace: print 'show/close_or_unload- unloading current from' ,self.ending_reason
                    self.current_player.unload()
                else:
                    if self.trace: print 'show/close_or_unload - closing current from'  ,self.ending_reason
                    self.current_player.close(None)
            self._wait_for_end()
        else:
            # current_player is None because closed further down show stack
            if self.trace: print 'show ended with current_player=None because ',self.ending_reason
            if self.ending_reason == 'killed':
                self.base_close_previous()

            elif self.ending_reason == 'error':
                self.base_close_previous()

            elif self.ending_reason == 'exit':
                self.end('normal',"show quit by exit command")

            elif self.ending_reason == 'user-stop':
                self.end('normal',"show quit by stop operation")
                    
            else:
                self.mon.err(self,"Unhandled ending_reason: ")
                self.end('error',"Unhandled ending_reason")          


    def _base_closed_callback_current(self,status,message):
        if self.trace: print 'show/closed_callback current is None  - was',self.current_player


    # wait for unloading or closing to complete then end
    def _wait_for_end(self):
        if self.trace: print 'show/wait_for_end',self.current_player
        if self.current_player is not None:
            if self.trace: print 'show/wait_for_end - play state is ',self.current_player.get_play_state()
            if self.current_player.play_state not in ('unloaded','closed','initialised','load-failed'):
                self.canvas.after(50,self._wait_for_end)
            else:
                if self.trace: print 'show/wait_for_end - current closed ', self.current_player,self.ending_reason
         
                if self.ending_reason == 'killed':
                    self.current_player.hide()
                    self.current_player=None
                    self.base_close_previous()

                elif self.ending_reason == 'error':
                    self.current_player.hide()
                    self.current_player=None
                    self.base_close_previous()

                elif self.ending_reason == 'exit':
                    self.current_player.hide()
                    self.current_player=None
                    self.base_close_previous()
                    
                elif self.ending_reason == 'show-timeout':
                    self.current_player.hide()
                    self.current_player=None
                    self.end('normal',"show timeout")
                    
                elif self.ending_reason == 'user-stop':
                    self.end('normal',"show quit by stop operation")
                    
                else:
                    self.mon.err(self,"Unhandled ending_reason: ")
                    self.end('error',"Unhandled ending_reason")
        else:
            if self.trace: print 'show/wait_for_end - current is None ', self.current_player,self.ending_reason


# ***************************
# end of show 
# ***************************

    # dummy, normally overidden by derived class
    def end(self,reason,message):
        self.mon.err(self,"end not overidden")
        self.base_end('error',message)

    def base_end(self,reason,message):
        if self.trace: print 'show/end at level ',self.level
        if self.trace: print 'show/end - Current is ',self.current_player
        if self.trace: print 'show/end - Previous is ',self.previous_player
        if self.trace: print 'SHOW/END with reason',reason
        if self.trace: print '\n\n'
        self.mon.log(self,self.show_params['show-ref']+ ' '+ str(self.show_id)+ ": Ending Show")
        self.end_callback(self.show_id,reason,message)
        self=None


    def base_subshow_ended_callback(self):
        # called by end_shower of a parent show  to get the last track of the subshow
        if self.trace: print 'show/subshow_ended_callback returns ',self.current_player
        return self.current_player


# ********************************
# Respond to external events
# ********************************


    def base_close_previous(self):
        if self.trace: print 'show/base_close_previous ',self
        # close the player from the previous track
        if self.previous_player is not  None:
            if self.trace: print 'show/previous not None',self.previous_player
            if self.previous_player.get_play_state() == 'showing':
                # showing or frozen
                if self.trace: print 'show/closing previous',self.previous_player
                self.previous_player.close(self._base_close_previous_callback)
            else:
                if self.trace: print 'show/previous is not showing'
                self.previous_player.hide()
                self.previous_player=None
                self.end(self.ending_reason,'')
        else:
            if self.trace: print 'show/previous is None'
            self.end(self.ending_reason,'')
            
                

    def _base_close_previous_callback(self,status,message):
        if self.trace: print 'show/close_previous callback, previous is None  - was',self.previous_player
        self.previous_player.hide()
        self.previous_player=None
        self.end(self.ending_reason,'')


    # exit received from external source
    def base_exit(self):
        self.mon.log(self,self.show_params['show-ref']+ ' '+ str(self.show_id)+ ": Exit received")
        if self.trace: print 'show/exit ',self
        # set signal to exit the show when all  sub-shows and players have ended
        self.exit_signal=True
        # then stop subshow or tracks.
        if self.shower is not None:
            self.shower.exit()
        elif self.current_player is not None:
            self.current_player.input_pressed('stop')
        else:
            self.end('normal','exit by ShowManager')

    # show timeout callback received
    def base_show_timeout_stop(self):
        if self.trace: print 'show/base_show_timeout_stop ',self
        # set signal to exit the show when all  sub-shows and players have ended
        self.show_timeout_signal=True
        # then stop and shows or tracks.
        if self.shower is not None:
            self.shower.show_timeout_stop()
        elif self.current_player is not None:
            self.current_player.input_pressed('stop')
        else:
            self.end('normal','stopped by Show Timeout')


    # dummy, normally overidden by derived class
    def terminate(self):
        self.mon.err(self,"terminate not overidden")
        self.base_end('error',"terminate not overidden")

    # terminate Pi Presents
    def base_terminate(self):
        if self.trace: print 'show/base_terminate ',self
        # set signal to stop the show when all  sub-shows and players have ended
        self.terminate_signal=True
        if self.shower is not None:
            self.shower.terminate()
        elif self.current_player is not None:
            self.ending_reason='killed'
            Show.base_close_or_unload(self)
        else:
            self.end('killed',' terminated with no shower or player to terminate')


  # respond to input events
    def base_input_pressed(self,symbol,edge,source):
        self.mon.log(self, self.show_params['show-ref']+ ' '+ str(self.show_id)+": received input event: " + symbol)

        if self.shower is not None:
            self.shower.input_pressed(symbol,edge,source)
        else:
            self.input_pressed_this_show(symbol,edge,source)
            


# ******************************
# reading resources.cfg
# ******************************

    def base_resource(self,section,item):
        value=self.rr.get(section,item)
        if value is False:
            self.mon.err(self, "resource: "+section +': '+ item + " not found" )
            self.terminate('error')
        else:
            return value


# ******************************
# lookup controls 
# *********************************
    def base_lookup_control(self,symbol,controls_list):
        for control in controls_list:
            if symbol == control[0]:
                return control[1]
        # not found so must be a trigger
        return ''

# ******************************
# Eggtimer
# *********************************
        
    def display_eggtimer(self,text):
        if text != '':
            self.egg_timer=self.canvas.create_text(int(self.show_params['eggtimer-x'])+ self.show_canvas_x1,
                                                   int(self.show_params['eggtimer-y']) + self.show_canvas_y1,
                                                   text= text,
                                                   fill=self.show_params['eggtimer-colour'],
                                                   font=self.show_params['eggtimer-font'],
                                                   anchor='nw')
            
            self.canvas.update_idletasks( )


    def delete_eggtimer(self):
        if self.egg_timer is not None:
            self.canvas.delete(self.egg_timer)
            self.egg_timer=None
            self.canvas.update_idletasks( )



# ******************************
# Display Admin Messages
# *********************************

    def display_admin_message(self,text):

        self.admin_message=self.canvas.create_text(int(self.show_params['eggtimer-x']) + self.show_canvas_x1,
                                                   int(self.show_params['eggtimer-y'])+self.show_canvas_y1,
                                                   text= text,
                                                   fill=self.show_params['eggtimer-colour'],
                                                   font=self.show_params['eggtimer-font'],
                                                   anchor='nw')
            
        self.canvas.update_idletasks( )


    def delete_admin_message(self):
        if self.admin_message is not None:
            self.canvas.delete(self.admin_message)
            self.canvas.update_idletasks( )


# ******************************
# utilities
# ******************************        



    def base_complete_path(self,track_file):
        #  complete path of the filename of the selected entry
        if track_file != '' and track_file[0]=="+":
            track_file=self.pp_home+track_file[1:]
        self.mon.log(self,"Track to load is: "+ track_file)
        return track_file     
  

    def calculate_duration(self,line):
        fields=line.split(':')
        if len(fields)==1:
            secs=fields[0]
            minutes='0'
            hours='0'
        if len(fields)==2:
            secs=fields[1]
            minutes=fields[0]
            hours='0'
        if len(fields)==3:
            secs=fields[2]
            minutes=fields[1]
            hours=fields[0]
        self.duration=3600*long(hours)+60*long(minutes)+long(secs)
        return ''


