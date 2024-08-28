require 'fileutils'
require 'syslog'

module MCollective
    module Agent
        class Filemanager<RPC::Agent
            action "move" do
                move
            end

            action "exist" do
                exist
            end

            action "copy_file" do
                copy_file
            end

            action "delete" do
                delete_file
            end

            action "pull_file" do
              implemented_by '/opt/mcollective/mcollective/agent/filemanager.py'
            end

            def log(log_name, *args)
                begin
                    logname = 'Filemanager.' + log_name
                    Syslog.open(logname)
                    Syslog.log(Syslog::LOG_INFO, *args)
                ensure
                    Syslog.close
                end
            end

            def move
                src =  request[:src]
                dest = request[:dest]
                begin
                    FileUtils.move(src, dest)
                    reply[:retcode] = 0
                rescue Exception => e
                    reply[:retcode] = 1
                    reply[:err] = "Failed to move #{src} to #{dest}: #{e}"
                end
            end
            
            def exist
                file = request[:file]
                reply[:out] = File.exist?(file)
                reply[:retcode] = 0
            end

            def copy_file
                src = request[:src]
                dest = request[:dest]
                self.log('copy_file', '%s', "Copying #{src} to #{dest}")
                begin
                    FileUtils.cp(src, dest)
                    reply[:retcode] = 0
                    reply[:out] = "Copied #{src} to #{dest}"
                    self.log('copy_file', '%s', "Copied #{src} to #{dest}")
                rescue Exception => ex
                    reply[:retcode] = 1
                    self.log('copy_file', '%s', "Failed to copy #{src} to #{dest}: #{ex.message}")
                    reply[:err] = "Failed to copy #{src} to #{dest}: #{ex.message}"
                end
            end

            def delete_file
                file = request[:file]
                self.log('delete_file', '%s', "Deleting #{file}")
                begin
                    if File.exist?(file)
                        File.delete(file)
                        reply[:out] = "Deleted #{file}"
                    end
                    reply[:retcode] = 0
                rescue Exception => ex
                    reply[:retcode] = 1
                    self.log('delete_file', '%s', "Failed to delete #{file}: #{ex.message}")
                    reply[:err] = "Failed to delete #{file}: #{ex.message}"
                end
            end
        end
    end
end
