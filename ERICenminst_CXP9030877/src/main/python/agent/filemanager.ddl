metadata    :name        => "filemanager",
            :description => "File Manager",
            :author      => "Ericsson AB",
            :license     => "Ericsson AB",
            :version     => "1.0",
            :url         => "",
            :timeout     => 42

action "move", :description => "Rename SOURCE to DEST, or move SOURCE(s) to DIRECTORY" do
    input   :src, 
            :prompt      => "src",
            :description => "Path to source file",
            :type        => :string,
            :validation  => '^.+$',
            :optional    => false,
            :maxlength   => 256

    input   :dest, 
            :prompt      => "dest",
            :description => "Path to destination file",
            :type        => :string,
            :validation  => '^.+$',
            :optional    => false,
            :maxlength   => 256

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "The stdout from running the command",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end

action "exist", :description => "Check if file exists" do
    input   :file, 
            :prompt      => "file",
            :description => "Path to a file",
            :type        => :string,
            :validation  => '^.+$',
            :optional    => false,
            :maxlength   => 256

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "Returns true if file exists, false if not",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end

action "copy_file" , :description => "Create a copy of a file" do
    display :always

    input  :src,
           :prompt      => "source",
           :description => "Path of file to copy",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :dest,
           :prompt      => "target",
           :description => "Path to copy file to",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "The stdout from running the command",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end

action "delete", :description => "Delete a files if it exists" do
    input   :file,
            :prompt      => "file",
            :description => "Path to a file",
            :type        => :string,
            :validation  => '^.+$',
            :optional    => false,
            :maxlength   => 256

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "Returns true if file exists, false if not",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end

action "pull_file", :description => "Pulls file content from consul kv store" do
    input   :consul_url,
            :prompt      => "consul_url",
            :description => "consul url",
            :type        => :string,
            :validation  => '^.+$',
            :optional    => false,
            :maxlength   => 0

    input   :file_path,
            :prompt      => "file_path",
            :description => "Path to a file",
            :type        => :string,
            :validation  => '^.+$',
            :optional    => false,
            :maxlength   => 256

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "Returns true if file exists, false if not",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end
