import os
from pp_gapshow import GapShow
from pp_livelist import LiveList
from pp_options import command_options

class LiveShow(GapShow):

    def __init__(self,
                 show_id,
                 show_params,
                 root,
                 canvas,
                 showlist,
                 pp_dir,
                 pp_home,
                 pp_profile):


        # init the common bits
        GapShow.__init__(self,
                         show_id,
                         show_params,
                         root,
                         canvas,
                         showlist,
                         pp_dir,
                         pp_home,
                         pp_profile)

        # control logging
        self.mon.on()
        
        # remove comment to trace this bottom level derived class
        # self.trace=True


        self.options=command_options()

        # get the livetracks directories
        self.pp_live_dir1 = self.pp_home + os.sep + 'pp_live_tracks'
        if not os.path.exists(self.pp_live_dir1):
            os.mkdir(self.pp_live_dir1)

        self.pp_live_dir2=''   
        if self.options['liveshow'] != '':
            self.pp_live_dir2 = self.options['liveshow']
            if not os.path.exists(self.pp_live_dir2):
                self.mon.err(self,"live tracks directory not found " + self.pp_live_dir2)
                self.end('error',"live tracks directory not found")

        # use the appropriate medialist
        self.medialist=LiveList()

        # and pass directories to livelist
        self.medialist.live_tracks(self.pp_live_dir1,self.pp_live_dir2)

