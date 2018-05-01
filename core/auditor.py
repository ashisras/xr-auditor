#!/usr/bin/env python

from lib.audit_helper import AuditHelpers
from pprint import pprint
import pdb
import subprocess
import sys, os
import shutil
import datetime
import xmltodict as xd
import time
import itertools
import argparse
from lib.audit_helper import XML_PREFIX_DOMAINS
from lib.audit_helper import COMPLIANCE_PREFIX

OPEN_FILE_WAIT_COUNT = 10
OPEN_FILE_WAIT_INTERVAL = 5


class IosxrAuditMain(AuditHelpers):

    def __init__(self,
         #        auditor_cfgfile=None,
                 *args, **kwargs):

        super(IosxrAuditMain, self).__init__(*args, **kwargs)

        if self.request_version:
            return None

        if "ROOT_LR_USER" in self.router_cfg_dict:
            if self.router_cfg_dict["ROOT_LR_USER"]:
                self.root_lr_user = self.router_cfg_dict["ROOT_LR_USER"]
                self.syslogger.info("Using root-lr user specified in auditor.cfg.yml, Username: "+ self.root_lr_user)
                self.logger.info("Using root-lr user specified in auditor.cfg.yml, Username: "+ self.root_lr_user)
            else:
                self.syslogger.info("Empty root-lr user specified in auditor.cfg.yml, Bailing out")
                self.logger.info("Empty root-lr user specified in auditor.cfg.yml, Bailing out")
                self.exit = True
        else:
            # Since user does not provide a root_lr_user,
            # determine it from the current running config

            result = self.xrcmd({"exec_cmd" : "show running-config username"})
            users_list = self.group_xr_users(result["output"])

            #Select the first user belonging to the root-lr group

            self.root_lr_user = ""
            user_found = False

            for user_config in users_list:
                if "group root-lr" in user_config:
                    for line in user_config:
                        if "username" in line:
                            self.root_lr_user = line.split()[1]
                            user_found = True
                            break
                else:
                    if self.debug:         
                        self.logger.debug("Not a root-lr user, continuing")
                if user_found:  
                    break

            if not user_found:
                self.syslogger.info("No root-lr user configured on the system, bailing out")
                self.exit = True
            else:
                self.syslogger.info("root-lr user discovered, Username: "+ self.root_lr_user)
                self.logger.info("root-lr user discovered, Username: "+ self.root_lr_user) 
 
    @classmethod
    def current_dir(self):
        if getattr(sys, 'frozen', False):
            # we are running in a bundle
            bundle_dir = sys._MEIPASS
        else:
            # we are running in a normal Python environment
            bundle_dir = os.path.dirname(os.path.abspath(__file__))
        return bundle_dir


    def group_xr_users(self, user_config_list=None, delimiter="!"):
        if user_config_list is None:
            self.syslogger.info("No user-config list provided")
            return [] 

        list_of_user_configs = [list(y) for x, y in 
                               itertools.groupby(user_config_list, 
                                                 lambda z: z == delimiter) if not x]
        
        return list_of_user_configs


    def _copy_file(self, src=None, dest=None):

        try:
            shutil.copy2(src, dest)
            # eg. src and dest are the same file
            return True
        except shutil.Error as e:
            self.syslogger.info("Failed to copy file, Error: %s" % e)
            # eg. source or destination doesn't exist
            return False 
        except IOError as e:
            self.syslogger.info('Failed to copy file, Error: %s' % e.strerror)
            return False


               
    def setup_xr_audit(self, srcfolder=None, dstfolder=None,appName=None, cronName=None, cronPrefix=None, outputXMLDir=None, uninstall=False, cleanxml=False):
                
        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["XR"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for XR audit app, defaulting to current_dir/xr/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/xr/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["XR"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for XR audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch" 

        if appName is None:
            try:
               appName = self.install_cfg_dict["XR"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for XR audit app, defaulting to audit_xr.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_xr.bin" 

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["XR"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for XR audit app, defaulting to audit_xr.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "audit_xr.cron" 

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["XR"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for XR audit cronjob, defaulting to audit_cron_xr_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_xr_"

        if outputXMLDir is None:
            try:
               outputXMLDir = self.install_cfg_dict["XR"]["output_xml_dir"]
            except Exception as e:
               self.syslogger.info("Failed to extract output xml directory for XR audit, defaulting to /misc/app_host")
               self.syslogger.info("Error is"+str(e))
               outputXMLDir = "/misc/app_host"

        if cleanxml:
            # Remove any accumulated xml files
            for xml_prefix in XML_PREFIX_DOMAINS+[COMPLIANCE_PREFIX]:
                result = self.run_bash("rm -f "+outputXMLDir+"/"+xml_prefix+"*")
                if not result["status"]:
                    check_removal = self.run_bash(cmd="ls "+outputXMLDir+"/")
                    if not check_removal["status"]: 
                        if xml_prefix in check_removal["output"]:
                            self.syslogger.info("Failed to remove existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir)
                            if self.debug:
                                self.logger.debug("Failed to remove existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir) 
                            return False
                        else:
                            self.syslogger.info("Removed existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir)
                            if self.debug:
                                self.logger.debug("Removed existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir) 
                            return True 
                    else:
                        self.syslogger.info("Failed to check removal of XML file with prefix: "+xml_prefix+" in  "+outputXMLDir)
                        if self.debug:
                            self.logger.debug("Failed to check removal of XML files in "+outputXMLDir)
                        return False
                else:
                    self.syslogger.info("Failed to remove XML file with prefix: "+xml_prefix+"in "+outputXMLDir)
                    if self.debug:
                        self.logger.debug("Failed to remove XML file with prefix: "+xml_prefix+"in "+outputXMLDir)      
                    return False



        wait_count = 0
        action_success = False


        file_exists = self.run_bash(cmd="ls "+dstfolder+"/")
        if not file_exists["status"]:
            if appName in file_exists["output"]:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False
     
        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.run_bash(cmd="lsof "+dstfolder+"/"+appName)
                self.syslogger.info(clean_up_filename)
                if self.debug:
                    self.logger.debug(clean_up_filename)
                if clean_up_filename["output"] is not "" :
                    # Process currently running, Sleep OPEN_FILE_WAIT_INTERVAL seconds before attempting again
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        result = self.run_bash(cmd="rm -f "+dstfolder+"/"+appName)
                        if result["status"]:
                            self.syslogger.info("Failed to remove xr audit app from XR LXC: "+appName)
                            self.syslogger.info("Retrying") 
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                        else:
                            self.syslogger.info("Removed xr audit app from XR LXC: "+appName)
                            self.logger.info("Removed xr audit app from XR LXC: "+appName)
                            action_success = True
                            break
                    else: 
                        if self._copy_file(srcfolder+"/"+appName, dstfolder+"/"+appName):
                            self.logger.info("XR LXC audit app successfully copied")
                            self.syslogger.info("XR LXC audit app successfully copied")
                            action_success = True
                            break
                        else:
                            self.syslogger.info("Retrying")
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                if self._copy_file(srcfolder+"/"+appName, dstfolder+"/"+appName):
                    self.logger.info("XR LXC audit app successfully copied")
                    self.syslogger.info("XR LXC audit app successfully copied")
                else:
                    self.logger.info("Failed to copy the XR LXC audit app")
                    self.syslogger.info("Failed to copy the XR LXC audit app")
                    return False


        # Now Create the cron job in XR to periodically execute the XR LXC audit app

        with open(srcfolder+"/"+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/etc/cron.d", croncmd_fname=cronPrefix+"*", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up old XR audit cron jobs")
            
            # If uninstall is set, then just return from here and it accomplishes our cleanup goal
            if uninstall:
                return True

            cron_setup = self.cron_job(folder="/etc/cron.d", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add") 
        
            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to set up cron Job")
                return False
            
            self.logger.info("XR LXC audit cron job successfully set up")
            self.syslogger.info("XR LXC audit cron job successfully set up")
        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        return True



    def setup_admin_audit(self, srcfolder=None, dstfolder=None, appName=None, cronName=None, cronPrefix=None, uninstall=False):


        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["ADMIN"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for ADMIN audit app, defaulting to current_dir/admin/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/admin/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["ADMIN"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for Admin audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["ADMIN"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for ADMIN audit app, defaulting to audit_admin.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_admin.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["ADMIN"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for ADMIN audit app, defaulting to audit_admin.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "audit_admin.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["ADMIN"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for ADMIN audit cronjob, defaulting to audit_cron_admin_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_admin_"


        file_exists = self.active_adminruncmd(cmd="ls "+dstfolder)
        if file_exists["status"] == "success":
            cmd_out = file_exists["output"][3:-1]
            if appName in cmd_out:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        wait_count = 0
        action_success = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.active_adminruncmd(cmd="lsof "+dstfolder+"/"+appName)
                cmd_out = clean_up_filename["output"][3:-1]
                if cmd_out:
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        remove_from_admin = self.active_adminruncmd(cmd="rm -f "+dstfolder+"/"+appName)
                        if remove_from_admin["status"] == "success":
                            check_removal = self.active_adminruncmd(cmd="ls "+dstfolder)

                            if check_removal["status"] == "success":
                                if appName in check_removal["output"][3:-1]:
                                    self.syslogger.info("Failed to remove audit app from Admin LXC: "+appName)
                                    self.logger.info("Failed to remove audit app from Admin LXC: "+appName)
                                    time.sleep(OPEN_FILE_WAIT_INTERVAL) 
                                else:
                                    self.syslogger.info("Successfully removed audit app from Admin LXC: "+appName)
                                    self.logger.info("Successfully removed audit app from Admin LXC: "+appName)
                                    action_success = True
                                    break
                            else:
                                self.syslogger.info("Failed to initiate check of removal of audit app from Admin LXC: "+appName)
                                self.logger.info("Failed to initiate check of removal of audit app from Admin LXC: "+appName)
                                return False
                        else:
                            self.syslogger.info("Failed to initiate removal of audit app from Admin LXC: "+appName)
                            self.logger.info("Failed to initiate removal of audit app from Admin LXC: "+appName)
                            return False 
                    else:
                        transfer_to_admin = self.active_adminscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                        if transfer_to_admin["status"] == "success":
                            self.logger.info("Admin LXC audit app successfully copied")
                            self.syslogger.info("Admin LXC audit app successfully copied")
                            action_success = True
                            if self.debug:
                                self.logger.debug(transfer_to_admin["output"])
                            break
                        else:
                            self.syslogger.info("Failed to copy Admin LXC audit app, Error:")
                            self.syslogger.info(transfer_to_admin["output"])
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False     
        else:
            if not uninstall:
                transfer_to_admin = self.active_adminscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                if transfer_to_admin["status"] == "success":
                    self.logger.info("Admin LXC audit app successfully copied")
                    self.syslogger.info("Admin LXC audit app successfully copied")
                    if self.debug:
                        self.logger.debug(transfer_to_admin["output"])
                else:
                    self.syslogger.info("Failed to copy Admin LXC audit app, Error:")
                    self.syslogger.info(transfer_to_admin["output"])


             
        # Now Create the cron job in Admin LXC to periodically execute the Admin LXC audit app
       

        with open(srcfolder+'/'+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up temp admin audit cron jobs")

            # Clean up stale cron jobs in the admin /etc/cron.d

            admin_cron_cleanup = self.active_adminruncmd(cmd="rm -f /etc/cron.d/"+cronPrefix+"*")

            if admin_cron_cleanup["status"] == "success":
                check_admin_cron_cleanup = self.active_adminruncmd(cmd="ls /etc/cron.d/")

                if cronPrefix in check_admin_cron_cleanup["output"]:
                    self.syslogger.info("Failed to clean up stale cron jobs in admin shell under /etc/cron.d")
                    return False
                else:
                    self.syslogger.info("Successfully cleaned up old admin audit cron jobs")
                    
                    # If uninstall is set, then just return from here
                    if uninstall:
                        return True
            else:
                self.syslogger.info("Failed to initiate admin shell cron cleanup")
                return False


            # Set up the temp admin audit cron job before transfer to admin shell
                
            cron_setup = self.cron_job(folder="/misc/app_host", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to create admin LXC cron Job in /misc/app_host")
                return False
        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        # Finally copy the created cron file into admin LXC /etc/cron.d to activate it

        transfer_to_admin = self.active_adminscp(src="/misc/app_host/"+cron_fname, dest="/etc/cron.d/"+cron_fname)

        if transfer_to_admin["status"] == "success":
            self.logger.info("Admin LXC audit cron file successfully copied and activated")
            self.syslogger.info("Admin LXC audit cron file successfully copied and activated")
            if self.debug:
                self.logger.debug(transfer_to_admin["output"])

            # Remove the temp cron file in /misc/app_host
            post_activation_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

            if post_activation_cleanup["status"] == "success":
                self.syslogger.info("Successfully cleaned up temp admin audit cron jobs post activation")
            else:
                self.syslogger.info("Failed to clean up temp admin audit cron jobs post activation,logging but not bailing out")
        else:
            self.syslogger.info("Failed to copy Admin LXC audit cron file, Error: %s" % transfer_to_admin["output"])
            return False


        return True



    def setup_host_audit(self, srcfolder=None, dstfolder=None, appName=None, cronName=None, cronPrefix=None, uninstall=False):

        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["HOST"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for HOST audit app, defaulting to current_dir/host/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/host/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["HOST"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for HOST audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["HOST"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for HOST audit app, defaulting to audit_host.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_host.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["HOST"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for HOST audit app, defaulting to audit_host.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "audit_host.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["HOST"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for HOST audit cronjob, defaulting to audit_cron_host_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_host_"


        file_exists = self.active_hostcmd(cmd="ls "+dstfolder)
        if file_exists["status"] == "success":
            cmd_out = file_exists["output"][3:-1]
            if appName in cmd_out:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        wait_count = 0
        action_success = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.active_hostcmd(cmd="lsof "+dstfolder+"/"+appName)
                cmd_out = clean_up_filename["output"][3:-1]
                if cmd_out:
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        remove_from_host = self.active_hostcmd(cmd="rm -f "+dstfolder+"/"+appName)
                        if remove_from_host["status"] == "success":
                            check_removal = self.active_hostcmd(cmd="ls "+dstfolder)

                            if check_removal["status"] == "success":
                                if appName in check_removal["output"][3:-1]:
                                    self.syslogger.info("Failed to remove audit app from HOST: "+appName)
                                    self.logger.info("Failed to remove audit app from HOST: "+appName)
                                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                                else:
                                    self.syslogger.info("Successfully removed audit app from HOST: "+appName)
                                    self.logger.info("Successfully removed audit app from HOST: "+appName)
                                    action_success = True
                                    break
                            else:
                                self.syslogger.info("Failed to initiate check of removal of audit app from HOST: "+appName)
                                self.logger.info("Failed to initiate check of removal of audit app from HOST: "+appName)
                                return False
                        else:
                            self.syslogger.info("Failed to initiate removal of audit app from HOST: "+appName)
                            self.logger.info("Failed to initiate removal of audit app from Admin HOST: "+appName)
                            return False
                    else:
                        transfer_to_host = self.active_hostscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                        if transfer_to_host["status"] == "success":
                            self.logger.info("HOST audit app successfully copied")
                            self.syslogger.info("HOST LXC audit app successfully copied")
                            action_success = True
                            if self.debug:
                                self.logger.debug(transfer_to_host["output"])
                            break
                        else:
                            self.syslogger.info("Failed to copy HOST audit app, Error:")
                            self.syslogger.info(transfer_to_host["output"])
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                transfer_to_host = self.active_hostscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                if transfer_to_host["status"] == "success":
                    self.logger.info("HOST audit app successfully copied")
                    self.syslogger.info("HOST audit app successfully copied")
                    if self.debug:
                        self.logger.debug(transfer_to_host["output"])
                else:
                    self.syslogger.info("Failed to copy Admin LXC audit app, Error:")
                    self.syslogger.info(transfer_to_host["output"])



        # Now Create the cron job in host layer to periodically execute the host audit app
       

        with open(srcfolder + '/'+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up temp host audit cron jobs")

            # Clean up stale cron jobs in the host /etc/cron.d

            host_cron_cleanup = self.active_hostcmd(cmd="rm -f /etc/cron.d/"+cronPrefix+"*")

            if host_cron_cleanup["status"] == "success":
                check_host_cron_cleanup = self.active_hostcmd(cmd="ls /etc/cron.d/")

                if cronPrefix in check_host_cron_cleanup["output"]:
                    self.syslogger.info("Failed to clean up stale cron jobs in host shell under /etc/cron.d")
                    return False
                else:
                    self.syslogger.info("Successfully cleaned up old host audit cron jobs")
                    # If uninstall is set, then just return from here
                    if uninstall:
                        return True
            else:
                self.syslogger.info("Failed to initiate host shell cron cleanup")
                return False


            cron_setup = self.cron_job(folder="/misc/app_host", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to create temp host audit cron job in /misc/app_host")
                return False

        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        # Finally copy the created cron file into host's /etc/cron.d to activate it

        transfer_to_host = self.active_hostscp(src="/misc/app_host/"+cron_fname, dest="/etc/cron.d/"+cron_fname)

        if transfer_to_host["status"] == "success":
            self.logger.info("Host audit cron file successfully copied and activated")
            self.syslogger.info("Host audit cron file successfully copied and activated")
            if self.debug:
                self.logger.debug(transfer_to_host["output"])

            # Remove the temp cron file in /misc/app_host
            post_activation_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

            if post_activation_cleanup["status"] == "success":
                self.syslogger.info("Successfully cleaned up temp admin audit cron jobs post activation")
            else:
                self.syslogger.info("Failed to clean up temp admin audit cron jobs post activation,logging but not bailing out")
        else:
            self.syslogger.info("Failed to copy and activate Host audit cron file, Error: %s" % transfer_to_host["output"])
            return False


        return True



    def setup_standby_auditor(self, srcfolder=None, dstfolder=None, appName=None, uninstall=False):

        if not self.ha_setup:
            self.syslogger.info("Standby RP not present, bailing out")
            return False


        if srcfolder is None:
            try:
               srcfolder = self.install_cfg_dict["STANDBY_INSTALLER"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for auditor app, defaulting to /misc/scratch/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = "/misc/scratch/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["STANDBY_INSTALLER"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for XR audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["STANDBY_INSTALLER"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for XR audit app, defaulting to audit_xr.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "auditor"


        if uninstall:
            remove_from_standby_xr = self.standby_xrruncmd(cmd="rm -f "+dstfolder+"/"+appName)
            if remove_from_standby_xr["status"] == "success":
                check_removal = self.standby_xrruncmd(cmd="ls "+dstfolder)

                if check_removal["status"] == "success":
                    if appName in check_removal["output"]:
                        self.syslogger.info("Failed to remove auditor app from Standby XR LXC: "+appName)
                        self.logger.info("Failed to remove auditor app from Standby XR LXC: "+appName)
                        return False
                    else:
                        self.syslogger.info("Successfully removed auditor app from Standby XR LXC: "+appName)
                        self.logger.info("Successfully removed auditor app from Standby XR LXC "+appName)
                        return True 
                else:
                    self.syslogger.info("Failed to initiate check of removal of auditor app from Standby XR LXC: "+appName)
                    self.logger.info("Failed to initiate check of removal of auditor app from Standby XR LXC: "+appName)
                    return False
            else:
                self.syslogger.info("Failed to initiate removal of auditor app from Standby XR LXC: "+appName)
                self.logger.info("Failed to initiate removal of auditor app from Standby XR LXC: "+appName)
                return False
        else:
            transfer_to_standby_xr = self.standby_xrscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
            if transfer_to_standby_xr["status"] == "success":
                self.logger.info("Standby XR LXC auditor app successfully copied")
                self.syslogger.info("Standby LXC auditor app successfully copied")
                if self.debug:
                    self.logger.debug(transfer_to_standby_xr["output"])
                return True
            else:
                self.syslogger.info("Failed to copy auditor app to standby XR LXC, Error:")
                self.syslogger.info(transfer_to_standby_xr["output"])
                return False



    def setup_standby_xr_audit(self, srcfolder=None, dstfolder=None, appName=None, cronName=None, cronPrefix=None, outputXMLDir = None, uninstall=False, cleanxml=False):

        if not self.ha_setup:
            self.syslogger.info("Standby RP not present, bailing out")
            return False

        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["XR"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for XR audit app, defaulting to current_dir/xr/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/xr/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["XR"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for XR audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["XR"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for XR audit app, defaulting to audit_xr.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_xr.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["XR"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for XR audit app, defaulting to audit_xr.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "audit_xr.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["XR"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for XR audit cronjob, defaulting to audit_cron_xr_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_xr_"


        if outputXMLDir is None:
            try:
               outputXMLDir = self.install_cfg_dict["XR"]["output_xml_dir"]
            except Exception as e:
               self.syslogger.info("Failed to extract output xml directory for XR audit, defaulting to /misc/app_host")
               self.syslogger.info("Error is"+str(e))
               outputXMLDir = "/misc/app_host"

        if cleanxml:
            # Remove any accumulated xml files
            for xml_prefix in XML_PREFIX_DOMAINS+[COMPLIANCE_PREFIX]:
                result = self.standby_xrruncmd("rm -f "+outputXMLDir+"/"+xml_prefix+"*")
                if result["status"] == "success":
                    check_removal = self.standby_xrruncmd(cmd="ls "+outputXMLDir+"/")
                    if check_removal["status"] == "success":
                        if xml_prefix in check_removal["output"]:
                            self.syslogger.info("Failed to remove existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir)
                            if self.debug:
                                self.logger.debug("Failed to remove existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir)
                            return False
                        else:
                            self.syslogger.info("Removed existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir)
                            if self.debug:
                                self.logger.debug("Removed existing XML file with prefix: "+xml_prefix+" in "+outputXMLDir)
                            return True
                    else:
                        self.syslogger.info("Failed to check removal of XML file with prefix: "+xml_prefix+" in  "+outputXMLDir)
                        if self.debug:
                            self.logger.debug("Failed to check removal of XML files in "+outputXMLDir)
                        return False
                else:
                    self.syslogger.info("Failed to remove XML file with prefix: "+xml_prefix+"in "+outputXMLDir)
                    if self.debug:
                        self.logger.debug("Failed to remove XML file with prefix: "+xml_prefix+"in "+outputXMLDir)
                    return False


        file_exists = self.standby_xrruncmd(cmd="ls "+dstfolder)
        if file_exists["status"] == "success":
            cmd_out = file_exists["output"]
            if appName in cmd_out:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        wait_count = 0
        action_success = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.standby_xrruncmd(cmd="lsof "+dstfolder+"/"+appName)
                cmd_out = clean_up_filename["output"]
                if cmd_out:
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        remove_from_standby_xr = self.standby_xrruncmd(cmd="rm -f "+dstfolder+"/"+appName)
                        if remove_from_standby_xr["status"] == "success":
                            check_removal = self.standby_xrruncmd(cmd="ls "+dstfolder)

                            if check_removal["status"] == "success":
                                if appName in check_removal["output"]:
                                    self.syslogger.info("Failed to remove audit app from Standby XR LXC: "+appName)
                                    self.logger.info("Failed to remove audit app from Standby XR LXCT: "+appName)
                                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                                else:
                                    self.syslogger.info("Successfully removed audit app from Standby XR LXC: "+appName)
                                    self.logger.info("Successfully removed audit app from Standby XR LXC "+appName)
                                    action_success = True
                                    break
                            else:
                                self.syslogger.info("Failed to initiate check of removal of audit app from Standby XR LXC: "+appName)
                                self.logger.info("Failed to initiate check of removal of audit app from Standby XR LXC: "+appName)
                                return False
                        else:
                            self.syslogger.info("Failed to initiate removal of audit app from Standby XR LXC: "+appName)
                            self.logger.info("Failed to initiate removal of audit app from Standby XR LXC: "+appName)
                            return False
                    else:
                        transfer_to_standby_xr = self.standby_xrscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                        if transfer_to_standby_xr["status"] == "success":
                            self.logger.info("Standby XR LXC audit app successfully copied")
                            self.syslogger.info("Standby LXC audit app successfully copied")
                            action_success = True
                            if self.debug:
                                self.logger.debug(transfer_to_standby_xr["output"])
                            break
                        else:
                            self.syslogger.info("Failed to copy XR LXC audit app to standby, Error:")
                            self.syslogger.info(transfer_to_standby_xr["output"])
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                transfer_to_standby_xr = self.standby_xrscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                if transfer_to_standby_xr["status"] == "success":
                    self.logger.info("Standby XR LXC  audit app successfully copied")
                    self.syslogger.info("Standby XR LXC  audit app successfully copied")
                    if self.debug:
                        self.logger.debug(transfer_to_standby_xr["output"])
                else:
                    self.syslogger.info("Failed to copy Standby XR LXC audit app, Error:")
                    self.syslogger.info(transfer_to_standby_xr["output"])


        # Now Create the cron job in Standby XR LXC to periodically execute the XR LXC audit app


        with open(srcfolder+"/"+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up temp standby XR LXC audit cron jobs")

            # Clean up stale cron jobs in the standby XR LXC /etc/cron.d

            standby_xr_cron_cleanup = self.standby_xrruncmd(cmd="rm -f /etc/cron.d/"+cronPrefix+"\*")

            if standby_xr_cron_cleanup["status"] == "success":
                check_standby_xr_cron_cleanup = self.standby_xrruncmd(cmd="ls /etc/cron.d/")

                if cronPrefix in check_standby_xr_cron_cleanup["output"]:
                    self.syslogger.info("Failed to clean up stale cron jobs in standby XR LXC shell under /etc/cron.d")
                    return False
                else:
                    self.syslogger.info("Successfully cleaned up old standby XR LXC audit cron jobs")
                   
                    # If uninstall is set, then just return from here
                    if uninstall:
                        return True
            else:
                self.syslogger.info("Failed to initiate standby XR LXC shell cron cleanup")
                return False


            # Set up the temp XR audit cron job before transfer to standby XR LXC shell

            cron_setup = self.cron_job(folder="/misc/app_host", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to create standby XR LXC cron Job in /misc/app_host")
                return False
        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        # Finally copy the created cron file into standby XR LXC /etc/cron.d to activate it

        transfer_to_standby_xr = self.standby_xrscp(src="/misc/app_host/"+cron_fname, dest="/etc/cron.d/"+cron_fname)

        if transfer_to_standby_xr["status"] == "success":
            self.logger.info("Standby XR LXC audit cron file successfully copied and activated")
            self.syslogger.info("Standby XR LXC audit cron file successfully copied and activated")
            if self.debug:
                self.logger.debug(transfer_to_standby_xr["output"])

            # Remove the temp cron file in /misc/app_host
            post_activation_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

            if post_activation_cleanup["status"] == "success":
                self.syslogger.info("Successfully cleaned up temp admin audit cron jobs post activation")
            else:
                self.syslogger.info("Failed to clean up temp admin audit cron jobs post activation,logging but not bailing out")

        else:
            self.syslogger.info("Failed to copy standby XR LXC audit cron file, Error: %s" % transfer_to_standby_xr["output"])
            return False

        return True




    def setup_standby_admin_audit(self, srcfolder=None, dstfolder=None, appName=None, cronName=None, cronPrefix=None, uninstall=False):

        if not self.ha_setup:
            self.syslogger.info("Standby RP not present, bailing out")
            return False


        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["ADMIN"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for ADMIN audit app, defaulting to current_dir/admin/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/admin/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["ADMIN"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for Admin audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["ADMIN"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for ADMIN audit app, defaulting to audit_admin.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_admin.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["ADMIN"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for ADMIN audit app, defaulting to audit_admin.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "audit_admin.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["ADMIN"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for ADMIN audit cronjob, defaulting to audit_cron_admin_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_admin_"



        file_exists = self.standby_adminruncmd(cmd="ls "+dstfolder)
        if file_exists["status"] == "success":
            cmd_out = file_exists["output"][3:-1]
            if appName in cmd_out:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        wait_count = 0
        action_success = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.standby_adminruncmd(cmd="lsof "+dstfolder+"/"+appName)
                cmd_out = clean_up_filename["output"][3:-1]
                if cmd_out:
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        remove_from_standby_admin = self.standby_adminruncmd(cmd="rm -f "+dstfolder+"/"+appName)
                        if remove_from_standby_admin["status"] == "success":
                            check_removal = self.standby_adminruncmd(cmd="ls "+dstfolder)

                            if check_removal["status"] == "success":
                                if appName in check_removal["output"][3:-1]:
                                    self.syslogger.info("Failed to remove audit app from Standby RP's Admin LXC: "+appName)
                                    self.logger.info("Failed to remove audit app from Standby RP's Admin LXC: "+appName)
                                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                                else:
                                    self.syslogger.info("Successfully removed audit app from Standby RP's Admin LXC: "+appName)
                                    self.logger.info("Successfully removed audit app from Standby RP's Admin LXC: "+appName)
                                    action_success = True
                                    break
                            else:
                                self.syslogger.info("Failed to initiate check of removal of audit app from Standby RP's Admin LXC: "+appName)
                                self.logger.info("Failed to initiate check of removal of audit app from Standby RP's Admin LXC: "+appName)
                                return False
                        else:
                            self.syslogger.info("Failed to initiate removal of audit app from Standby RP's Admin LXC: "+appName)
                            self.logger.info("Failed to initiate removal of audit app from Standby RP's Admin LXC: "+appName)
                            return False
                    else:
                        transfer_to_standby_admin = self.standby_adminscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                        if transfer_to_standby_admin["status"] == "success":
                            self.logger.info("Standby RP Admin LXC audit app successfully copied")
                            self.syslogger.info("Standby RP Admin LXC audit app successfully copied")
                            action_success = True
                            if self.debug:
                                self.logger.debug(transfer_to_standby_admin["output"])
                            break
                        else:
                            self.syslogger.info("Failed to copy Standby RP Admin LXC audit app, Error:")
                            self.syslogger.info(transfer_to_standby_admin["output"])
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                transfer_to_standby_admin = self.standby_adminscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                if transfer_to_standby_admin["status"] == "success":
                    self.logger.info("Standby Admin LXC audit app successfully copied")
                    self.syslogger.info("Standby Admin LXC audit app successfully copied")
                    if self.debug:
                        self.logger.debug(transfer_to_standby_admin["output"])
                else:
                    self.syslogger.info("Failed to copy Standby RP Admin LXC audit app, Error:")
                    self.syslogger.info(transfer_to_standby_admin["output"])


        # Now Create the cron job in standby Admin LXC to periodically execute the Admin LXC audit app


        with open(srcfolder+"/"+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up temp admin audit cron jobs")

            # Clean up stale cron jobs in the standby admin /etc/cron.d

            standby_admin_cron_cleanup = self.standby_adminruncmd(cmd="rm -f /etc/cron.d/"+cronPrefix+"\*")

            if standby_admin_cron_cleanup["status"] == "success":
                check_standby_admin_cron_cleanup = self.standby_adminruncmd(cmd="ls /etc/cron.d/")

                if cronPrefix in check_standby_admin_cron_cleanup["output"]:
                    self.syslogger.info("Failed to clean up stale cron jobs in standby admin LXC shell under /etc/cron.d")
                    return False
                else:
                    self.syslogger.info("Successfully cleaned up old admin audit cron jobs")
                    # If uninstall is set, then just return from here
                    if uninstall:
                        return True
            else:
                self.syslogger.info("Failed to initiate Standby admin LXC shell cron cleanup")
                return False


            # Set up the temp admin audit cron job before transfer to Standby Admin LXCshell

            cron_setup = self.cron_job(folder="/misc/app_host", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to create standby admin LXC cron Job in /misc/app_host")
                return False
        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        # Finally copy the created cron file into admin LXC /etc/cron.d to activate it

        transfer_to_standby_admin = self.standby_adminscp(src="/misc/app_host/"+cron_fname, dest="/etc/cron.d/"+cron_fname)

        if transfer_to_standby_admin["status"] == "success":
            self.logger.info("Standby Admin LXC audit cron file successfully copied and activated")
            self.syslogger.info("Standby Admin LXC audit cron file successfully copied and activated")
            if self.debug:
                self.logger.debug(transfer_to_standby_admin["output"])

            # Remove the temp cron file in /misc/app_host
            post_activation_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

            if post_activation_cleanup["status"] == "success":
                self.syslogger.info("Successfully cleaned up temp admin audit cron jobs post activation")
            else:
                self.syslogger.info("Failed to clean up temp admin audit cron jobs post activation,logging but not bailing out")

        else:
            self.syslogger.info("Failed to copy Standby Admin LXC audit cron file, Error: %s" % transfer_to_standby_admin["output"])
            return False

        return True



    def setup_standby_host_audit(self, srcfolder=None, dstfolder=None, appName=None, cronName=None, cronPrefix=None, uninstall=False):

        if not self.ha_setup:
            self.syslogger.info("Standby RP not present, bailing out")
            return False


        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["HOST"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for HOST audit app, defaulting to current_dir/host/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/host/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["HOST"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for HOST audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["HOST"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for HOST audit app, defaulting to audit_host.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_host.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["HOST"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for HOST audit app, defaulting to audit_host.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "audit_host.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["HOST"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for HOST audit cronjob, defaulting to audit_cron_host_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_host_"



        file_exists = self.standby_hostcmd(cmd="ls "+dstfolder)
        if file_exists["status"] == "success":
            cmd_out = file_exists["output"][3:-1]
            if appName in cmd_out:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        wait_count = 0
        action_success = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.standby_hostcmd(cmd="lsof "+dstfolder+"/"+appName)
                cmd_out = clean_up_filename["output"][3:-1]
                if cmd_out:
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        remove_from_standby_host = self.standby_hostcmd(cmd="rm -f "+dstfolder+"/"+appName)
                        if remove_from_standby_host["status"] == "success":
                            check_removal = self.standby_hostcmd(cmd="ls "+dstfolder)

                            if check_removal["status"] == "success":
                                if appName in check_removal["output"][3:-1]:
                                    self.syslogger.info("Failed to remove audit app from Standby RP's HOST shell: "+appName)
                                    self.logger.info("Failed to remove audit app from Standby RP's HOST shell: "+appName)
                                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                                else:
                                    self.syslogger.info("Successfully removed audit app from Standby RP's HOST shell: "+appName)
                                    self.logger.info("Successfully removed audit app from Standby RP's HOST shell: "+appName)
                                    action_success = True
                                    break
                            else:
                                self.syslogger.info("Failed to initiate check of removal of audit app from Standby RP's HOST shell: "+appName)
                                self.logger.info("Failed to initiate check of removal of audit app from Standby RP's HOST shell: "+appName)
                                return False
                        else:
                            self.syslogger.info("Failed to initiate removal of audit app from Standby RP's HOST shell: "+appName)
                            self.logger.info("Failed to initiate removal of audit app from Standby RP's HOST shell: "+appName)
                            return False
                    else:
                        transfer_to_standby_host = self.standby_hostscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                        if transfer_to_standby_host["status"] == "success":
                            self.logger.info("Standby RP HOST audit app successfully copied")
                            self.syslogger.info("Standby RP HOST audit app successfully copied")
                            action_success = True
                            if self.debug:
                                self.logger.debug(transfer_to_standby_host["output"])
                            break
                        else:
                            self.syslogger.info("Failed to copy Standby RP HOST audit app, Error:")
                            self.syslogger.info(transfer_to_standby_host["output"])
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                transfer_to_standby_host = self.standby_hostscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                if transfer_to_standby_host["status"] == "success":
                    self.logger.info("Standby HOST audit app successfully copied")
                    self.syslogger.info("Standby HOST audit app successfully copied")
                    if self.debug:
                        self.logger.debug(transfer_to_standby_host["output"])
                else:
                    self.syslogger.info("Failed to copy Standby HOST audit app, Error:")
                    self.syslogger.info(transfer_to_standby_host["output"])


        # Now Create the cron job in standby host to periodically execute the host audit app


        with open(srcfolder+"/"+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up temp host audit cron jobs")

            # Clean up stale cron jobs in the standby host /etc/cron.d

            standby_host_cron_cleanup = self.standby_hostcmd(cmd="rm -f /etc/cron.d/"+cronPrefix+"\*")

            if standby_host_cron_cleanup["status"] == "success":
                check_standby_host_cron_cleanup = self.standby_hostcmd(cmd="ls /etc/cron.d/")

                if cronPrefix in check_standby_host_cron_cleanup["output"]:
                    self.syslogger.info("Failed to clean up stale cron jobs in standby host shell under /etc/cron.d")
                    return False
                else:
                    self.syslogger.info("Successfully cleaned up old Standby host audit cron jobs")
                    # If uninstall is set, then just return from here
                    if uninstall:
                        return True
            else:
                self.syslogger.info("Failed to initiate Standby host shell cron cleanup")
                return False


            # Set up the temp admin audit cron job before transfer to Standby host shell

            cron_setup = self.cron_job(folder="/misc/app_host", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to create standby host cron Job in /misc/app_host")
                return False
        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        # Finally copy the created cron file into standby host /etc/cron.d to activate it

        transfer_to_standby_host = self.standby_hostscp(src="/misc/app_host/"+cron_fname, dest="/etc/cron.d/"+cron_fname)

        if transfer_to_standby_host["status"] == "success":
            self.logger.info("Standby host audit cron file successfully copied and activated")
            self.syslogger.info("Standby host audit cron file successfully copied and activated")
            if self.debug:
                self.logger.debug(transfer_to_standby_host["output"])

            # Remove the temp cron file in /misc/app_host
            post_activation_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

            if post_activation_cleanup["status"] == "success":
                self.syslogger.info("Successfully cleaned up temp standby host  audit cron jobs post activation")
            else:
                self.syslogger.info("Failed to clean up temp admin audit cron jobs post activation,logging but not bailing out")

        else:
            self.syslogger.info("Failed to copy Standby host audit cron file, Error: %s" % transfer_to_standby_host["output"])
            return False

        return True



    def setup_collector(self, srcfolder=None, dstfolder=None,appName=None, cronName=None, cronPrefix=None, uninstall=False):

        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["COLLECTOR"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for COLLECTOR audit app, defaulting to current_dir/host/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/collector/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["COLLECTOR"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for COLLECTOR audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["COLLECTOR"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for COLLECTOR app, defaulting to collector.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "collector.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["COLLECTOR"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for COLLECTOR audit app, defaulting to collector.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "collector.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["COLLECTOR"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for COLLECTOR audit cronjob, defaulting to audit_cron_collector_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_collector_"


        wait_count = 0
        action_success = False


        file_exists = self.run_bash(cmd="ls "+dstfolder)
        if not file_exists["status"]:
            if appName in file_exists["output"]:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.run_bash(cmd="lsof "+dstfolder+"/"+appName)
                self.syslogger.info(clean_up_filename)
                if self.debug:
                    self.logger.debug(clean_up_filename)

                if clean_up_filename["output"] is not "" :
                    # Process currently running, Sleep OPEN_FILE_WAIT_INTERVAL seconds before attempting again
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        result = self.run_bash(cmd="rm -f "+dstfolder+"/"+appName)
                        if result["status"]:
                            self.syslogger.info("Failed to remove Collector audit app from XR LXC: "+appName)
                            self.syslogger.info("Retrying")
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                        else:
                            self.syslogger.info("Removed Collector audit app from XR LXC: "+appName)
                            self.logger.info("Removed Collector audit app from XR LXC: "+appName)
                            action_success = True
                            break
                    else:
                        if self._copy_file(srcfolder+"/"+appName, dstfolder+"/"+appName):
                            self.logger.info("XR LXC Collector app successfully copied")
                            self.syslogger.info("XR LXC Collector  app successfully copied")
                            action_success = True
                            break
                        else:
                            self.syslogger.info("Retrying")
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                if self._copy_file(srcfolder+"/"+appName, dstfolder+"/"+appName):
                    self.logger.info("XR LXC Collector app successfully copied")
                    self.syslogger.info("XR LXC Collector app successfully copied")
                else:
                    self.logger.info("Failed to copy the XR LXC Collector app")
                    self.syslogger.info("Failed to copy the XR LXC Collector app")
                    return False



        # Create the cron job in XR to periodically collect the combined logs from XR LXC, Admin LXC and host 

        with open(srcfolder+"/"+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/etc/cron.d", croncmd_fname=cronPrefix+"*", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up old collector cron jobs")

            # If uninstall is set, then just return from here
            if uninstall:
                return True

            cron_setup = self.cron_job(folder="/etc/cron.d", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to set up cron Job")
                return False

            self.logger.info("Collector cron job successfully set up in XR LXC")
            self.syslogger.info("Collector cron job successfully set up in XR LXC")

        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        return True



    def setup_standby_collector(self, srcfolder=None, dstfolder=None, appName=None, cronName=None, cronPrefix=None, uninstall=False):

        if not self.ha_setup:
            self.syslogger.info("Standby RP not present, bailing out")
            return False

        if srcfolder is None:
            try:
               srcfolder = IosxrAuditMain.current_dir()+"/"+self.install_cfg_dict["COLLECTOR"]["srcDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract src directory for COLLECTOR audit app, defaulting to current_dir/host/")
               self.syslogger.info("Error is"+str(e))
               srcfolder = IosxrAuditMain.current_dir()+"/collector/";

        if dstfolder is None:
            try:
               dstfolder = self.install_cfg_dict["COLLECTOR"]["appDir"]
            except Exception as e:
               self.syslogger.info("Failed to extract app directory for COLLECTOR audit app, defaulting to /misc/scratch")
               self.syslogger.info("Error is"+str(e))
               dstfolder = "/misc/scratch"

        if appName is None:
            try:
               appName = self.install_cfg_dict["COLLECTOR"]["appName"]
            except Exception as e:
               self.syslogger.info("Failed to extract app name for COLLECTOR audit app, defaulting to audit_collector.bin")
               self.syslogger.info("Error is"+str(e))
               appName = "audit_collector.bin"

        if cronName is None:
            try:
               cronName = self.install_cfg_dict["COLLECTOR"]["cronName"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronName for COLLECTOR audit app, defaulting to collector.cron")
               self.syslogger.info("Error is"+str(e))
               cronName = "collector.cron"

        if cronPrefix is None:
            try:
               cronPrefix = self.install_cfg_dict["COLLECTOR"]["cronPrefix"]
            except Exception as e:
               self.syslogger.info("Failed to extract cronPrefix for COLLECTOR audit cronjob, defaulting to audit_cron_collector_")
               self.syslogger.info("Error is"+str(e))
               cronPrefix = "audit_cron_collector_"


        file_exists = self.standby_xrruncmd(cmd="ls "+dstfolder)
        if file_exists["status"] == "success":
            cmd_out = file_exists["output"]
            if appName in cmd_out:
                app_exists = True
            else:
                app_exists = False
        else:
            self.syslogger.info("Failed to check if app exists already")
            app_exists = False

        wait_count = 0
        action_success = False

        if app_exists:
            while(wait_count < OPEN_FILE_WAIT_COUNT):
                clean_up_filename = self.standby_xrruncmd(cmd="lsof "+dstfolder+"/"+appName)
                cmd_out = clean_up_filename["output"]
                if cmd_out:
                    self.syslogger.info("Process currently running, wait "+str(OPEN_FILE_WAIT_INTERVAL)+" seconds before attempting again")
                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                else:
                    if uninstall:
                        remove_from_standby_xr = self.standby_xrruncmd(cmd="rm -f "+dstfolder+"/"+appName)
                        if remove_from_standby_xr["status"] == "success":
                            check_removal = self.standby_xrruncmd(cmd="ls "+dstfolder)

                            if check_removal["status"] == "success":
                                if appName in check_removal["output"]:
                                    self.syslogger.info("Failed to remove Collector app from Standby XR LXC: "+appName)
                                    self.logger.info("Failed to remove Collector app from Standby XR LXCT: "+appName)
                                    time.sleep(OPEN_FILE_WAIT_INTERVAL)
                                else:
                                    self.syslogger.info("Successfully removed Collector app from Standby XR LXC: "+appName)
                                    self.logger.info("Successfully removed Collector app from Standby XR LXC "+appName)
                                    action_success = True
                                    break
                            else:
                                self.syslogger.info("Failed to initiate check of removal of Collector app from Standby XR LXC: "+appName)
                                self.logger.info("Failed to initiate check of removal of Collector app from Standby XR LXC: "+appName)
                                return False
                        else:
                            self.syslogger.info("Failed to initiate removal of Collector app from Standby XR LXC: "+appName)
                            self.logger.info("Failed to initiate removal of Collector app from Standby XR LXC: "+appName)
                            return False
                    else:
                        transfer_to_standby_xr = self.standby_xrscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                        if transfer_to_standby_xr["status"] == "success":
                            self.logger.info("Standby XR LXC Collector app successfully copied")
                            self.syslogger.info("Standby XR LXC Collector app successfully copied")
                            action_success = True
                            if self.debug:
                                self.logger.debug(transfer_to_standby_xr["output"])
                            break
                        else:
                            self.syslogger.info("Failed to copy Standby XR LXC  audit app, Error:")
                            self.syslogger.info(transfer_to_standby_xr["output"])
                            time.sleep(OPEN_FILE_WAIT_INTERVAL)
                wait_count = wait_count + 1

            if not action_success:
                return False
        else:
            if not uninstall:
                transfer_to_standby_xr = self.standby_xrscp(src=srcfolder+"/"+appName, dest=dstfolder+"/"+appName)
                if transfer_to_standby_xr["status"] == "success":
                    self.logger.info("Standby XR LXC Collector app successfully copied")
                    self.syslogger.info("Standby XR LXC Collector audit app successfully copied")
                    if self.debug:
                        self.logger.debug(transfer_to_standby_xr["output"])
                else:
                    self.syslogger.info("Failed to copy Standby XR LXC Collector app, Error:")
                    self.syslogger.info(transfer_to_standby_xr["output"])



        # Now Create the cron job in Standby XR LXC to periodically execute the XR LXC audit app


        with open(srcfolder+"/"+cronName, 'r') as f:
            cron_cmd = f.read()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        cron_fname = cronPrefix+timestamp


        cron_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

        if cron_cleanup["status"] == "success":
            self.syslogger.info("Successfully cleaned up temp standby XR LXC collector cron jobs")

            # Clean up stale cron jobs in the standby XR LXC /etc/cron.d

            standby_xr_cron_cleanup = self.standby_xrruncmd(cmd="rm -f /etc/cron.d/"+cronPrefix+"\*")

            if standby_xr_cron_cleanup["status"] == "success":
                check_standby_xr_cron_cleanup = self.standby_xrruncmd(cmd="ls /etc/cron.d/")

                if cronPrefix in check_standby_xr_cron_cleanup["output"]:
                    self.syslogger.info("Failed to clean up stale collector cron jobs in standby XR LXC shell under /etc/cron.d")
                    return False

                else:
                    self.syslogger.info("Successfully cleaned up old standby collector cron jobs")
                    # If uninstall is set, then just return from here
                    if uninstall:
                        return True
            else:
                self.syslogger.info("Failed to initiate standby XR LXC shell cron cleanup")
                return False


            # Set up the temp collector cron job before transfer to standby XR LXC shell

            cron_setup = self.cron_job(folder="/misc/app_host", croncmd = cron_cmd, croncmd_fname = cron_fname, action="add")

            if cron_setup["status"] == "error":
                self.syslogger.info("Unable to create standby XR LXC collector cron Job in /misc/app_host")
                return False
        else:
            self.syslogger.info("Failed to clean existing audit cron jobs")
            return False

        # Finally copy the created cron file into standby XR LXC /etc/cron.d to activate it

        transfer_to_standby_xr = self.standby_xrscp(src="/misc/app_host/"+cron_fname, dest="/etc/cron.d/"+cron_fname)

        if transfer_to_standby_xr["status"] == "success":
            self.logger.info("Standby XR LXC collector cron file successfully copied and activated")
            self.syslogger.info("Standby XR LXC collector cron file successfully copied and activated")
            if self.debug:
                self.logger.debug(transfer_to_standby_xr["output"])
 
            # Remove the temp cron file in /misc/app_host
            post_activation_cleanup = self.cron_job(folder="/misc/app_host", action="delete")

            if post_activation_cleanup["status"] == "success":
                self.syslogger.info("Successfully cleaned up temp Standby XR LXC collector cron jobs post activation")
            else:
                self.syslogger.info("Failed to clean up temp Standby XR LXC collector cron jobs post activation,logging but not bailing out")

        else:
            self.syslogger.info("Failed to copy standby XR LXC collector cron file, Error: %s" % transfer_to_standby_xr["output"])
            return False

        return True



if __name__ == "__main__":

    # Create an Object of the child class, syslog parameters are optional. 
    # If nothing is specified, then logging will happen to local log rotated file.



    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', action='store_true',
                    help='Display Current version of the Auditor app and exit')
    parser.add_argument('-i', '--install', action='store_true', dest='install',
                    help='Install the required artifacts (audit apps, collectors and cron jobs)\n to default locations or to those specified in auditor.cfg.yml')
    parser.add_argument('-u', '--uninstall', action='store_true', dest='uninstall',
                    help='Uninstall all the artifacts from the system based on auditor.cfg.yml settings')
    parser.add_argument('-d', '--debug', action='store_true',
                    help='Enable verbose logging')


    results = parser.parse_args()

    if not ( results.install or 
             results.uninstall or 
             results.version):
        parser.print_help()
        sys.exit(0)


    audit_obj = IosxrAuditMain(auditor_cfg=IosxrAuditMain.current_dir()+"/userfiles/auditor.cfg.yml",
                               compliance_xsd=IosxrAuditMain.current_dir()+"/userfiles/compliance.xsd",
                               domain="INSTALLER",
                               request_version=results.version)

    if results.version:
        if audit_obj.version:
            print audit_obj.version["version"]
            sys.exit(0)
        else:
            print "Failed to get version"
            sys.exit(1)

    if audit_obj.exit:
        audit_obj.syslogger.info("Exit flag is set, aborting")
        audit_obj.logger.info("Failed to run auditor, see /tmp/ztp_python.log for collected syslogs")
        sys.exit(1)

    if results.debug:
        audit_obj.toggle_debug(1)

    uninstall_flag = False

    if results.uninstall:
         uninstall_flag = True

    if audit_obj.debug:
        for root, directories, filenames in os.walk(IosxrAuditMain.current_dir()):
            for directory in directories:
                audit_obj.logger.debug(os.path.join(root, directory))
            for filename in filenames:
                audit_obj.logger.debug(os.path.join(root,filename))


    if not audit_obj.setup_xr_audit(uninstall=uninstall_flag):
        if not uninstall_flag:
            audit_obj.syslogger.info("Failed to setup XR LXC audit artifacts")
            audit_obj.logger.info("Failed to setup XR LXC audit artifacts")
        else:
            audit_obj.syslogger.info("Failed to remove XR LXC audit artifacts")
            audit_obj.logger.info("Failed to remove XR LXC audit artifacts")
        sys.exit(1)


    if not audit_obj.setup_admin_audit(uninstall=uninstall_flag):
        if not uninstall_flag:
            audit_obj.syslogger.info("Failed to setup ADMIN LXC audit artifacts")
            audit_obj.logger.info("Failed to setup ADMIN LXC audit artifacts")
        else:
            audit_obj.syslogger.info("Failed to remove ADMIN LXC audit artifacts")
            audit_obj.logger.info("Failed to remove ADMIN LXC audit artifacts")
        sys.exit(1)


    if not audit_obj.setup_host_audit(uninstall=uninstall_flag):
        if not uninstall_flag:
            audit_obj.syslogger.info("Failed to setup HOST audit artifacts")
            audit_obj.logger.info("Failed to setup HOST audit artifacts")
        else:
            audit_obj.syslogger.info("Failed to remove HOST audit artifacts")
            audit_obj.logger.info("Failed to remove XR HOST audit artifacts")
        sys.exit(1)



    if not audit_obj.setup_collector(uninstall=uninstall_flag):
        if not uninstall_flag:
            audit_obj.syslogger.info("Failed to setup COLLECTOR artifacts")
            audit_obj.logger.info("Failed to setup COLLECTOR artifacts")
        else:
            audit_obj.syslogger.info("Failed to remove COLLECTOR artifacts")
            audit_obj.logger.info("Failed to remove COLLECTOR artifacts")
        sys.exit(1)


    if uninstall_flag:
        # Clean up XMLs created on active RP XR LXC
        if not audit_obj.setup_xr_audit(cleanxml=True):
            audit_obj.syslogger.info("Failed to clean up Active RP XR LXC xml files")
            audit_obj.logger.info("Failed to clean up Active RP XR LXC xml files")
            sys.exit(1)



    if audit_obj.ha_setup:
 
        # Replicate itself to standby xr to make sure installer/uninstaller is available
        # post switchover on an HA(active/standby) setup

        if not audit_obj.setup_standby_auditor(uninstall=uninstall_flag):
            if not uninstall_flag:
                audit_obj.syslogger.info("Failed to setup auditor app on standby XR LXC")
                audit_obj.logger.info("Failed to setup auditor app on standby XR LXC")
            else:
                audit_obj.syslogger.info("Failed to remove auditor app on standby XR LXC")
                audit_obj.logger.info("Failed to remove auditor app on standby XR LXC")
            sys.exit(1)


        if not audit_obj.setup_standby_xr_audit(uninstall=uninstall_flag):
            if not uninstall_flag:
                audit_obj.syslogger.info("Failed to setup Standby XR LXC audit artifacts")
                audit_obj.logger.info("Failed to setup Standby XR LXC audit artifacts")
            else:
               audit_obj.syslogger.info("Failed to remove Standby XR LXC audit artifacts")
               audit_obj.logger.info("Failed to remove Standby XR LXC audit artifacts")
            sys.exit(1)


        if not audit_obj.setup_standby_admin_audit(uninstall=uninstall_flag):
            if not uninstall_flag:
                audit_obj.syslogger.info("Failed to setup Standby Admin LXC audit artifacts")
                audit_obj.logger.info("Failed to setup Standby Admin LXC audit artifacts")
            else:
                audit_obj.syslogger.info("Failed to remove Standby Admin LXC audit artifacts")
                audit_obj.logger.info("Failed to remove Standby Admin LXC audit artifacts")
            sys.exit(1)


        if not audit_obj.setup_standby_host_audit(uninstall=uninstall_flag):
            if not uninstall_flag:
                audit_obj.syslogger.info("Failed to setup Standby HOST audit artifacts")
                audit_obj.logger.info("Failed to setup Standby HOST audit artifacts")
            else:
                audit_obj.syslogger.info("Failed to remove Standby HOST audit artifacts")
                audit_obj.logger.info("Failed to remove Standby HOST audit artifacts")
            sys.exit(1)


        if not audit_obj.setup_standby_collector(uninstall=uninstall_flag):
            if not uninstall_flag:
                audit_obj.syslogger.info("Failed to setup Standby RP COLLECTOR artifacts")
                audit_obj.logger.info("Failed to setup Standby RP COLLECTOR artifacts")
            else:
                audit_obj.syslogger.info("Failed to remove Standby RP COLLECTOR artifacts")
                audit_obj.logger.info("Failed to remove Standby RP COLLECTOR artifacts")
            sys.exit(1)


        if uninstall_flag:
            # Clean up XMLs created on active RP XR LXC
            if not audit_obj.setup_standby_xr_audit(cleanxml=True):
                audit_obj.syslogger.info("Failed to clean up Standby RP XR LXC XML files")
                audit_obj.logger.info("Failed to clean up Standby RP XR LXC XML files")
                sys.exit(1)

    if not uninstall_flag:
        audit_obj.syslogger.info("Successfully set up artifacts, IOS-XR Linux auditing is now ON")
        audit_obj.logger.info("Successfully set up artifacts, IOS-XR Linux auditing is now ON")
    else:
        audit_obj.syslogger.info("Successfully uninstalled all artifacts, IOS-XR Linux auditing is now OFF")
        audit_obj.logger.info("Successfully uninstalled artifacts, IOS-XR Linux auditing is now OFF")
    sys.exit(0)

