function form_request(form, method, skip_empty) {
    if (typeof skip_empty == 'undefined' || skip_empty == null)
        skip_empty = false;
    var files_to_upload = [];

    var js_form = form2js(form, '.', skip_empty, function(node) {
        /* Find any file input fields and add them to the files array */
        if (!node.nodeName.match(/INPUT/i) || !node.type.match(/file/i))
            return false;
        if (node.files.length > 0)
            files_to_upload.push({name: node.name, files: node.files});
        return false;
    });

    file_handler = new FileHandler(files_to_upload, js_form, function() {
        /* Only submit the form once all files have replaced by file_ids */
        var jsonified_form = JSON.stringify(js_form);
        console.log('About to submit');
        console.log(js_form);
        $.ajax({url: form.action, data: jsonified_form, type: method,
                complete: handle_response});
    });
    return false;  // Ensure the form submission doesn't actually happen
}


function handle_response(xhr) {
    if (xhr.status > 500) {
        console.log('Server error');
        console.log(xhr.responseText);
        return;
    }
    data = JSON.parse(xhr.responseText);
    switch(xhr.status) {
    case 200:  // Ok
        alert(data['message'])
        break;
    case 201:  // Created
        window.location = data['redir_location'];
        break;
    case 400:  // BadRequest
        msg = data['error']
        if (typeof data['messages'] === 'string')
            msg += '\n' + data['messages']
        else
            for (i in data['messages'])
                msg += '\n' + data['messages'][i]
        alert(msg);
        break;
    case 409:  // Conflict
        alert(data['message']);
        break;
        case 410:  // Gone
        window.location = data['redir_location'];
        break;
    default:
        alert("Unhandled status code: " + xhr.status);
    }
}

function FileHandler(to_replace, js_form, completed_callback) {
    this.to_replace = to_replace;
    this.js_form = js_form;
    this.completed_callback = completed_callback;
    this.current = null;
    this.upload_or_submit();
}

FileHandler.prototype.upload_or_submit = function() {
    this.current = this.to_replace.pop();
    if (this.current) {
        console.log('Attempting to replace ' + this.current.name);
        process_file(this);
    }
    else {
        this.completed_callback();
    }
}

FileHandler.prototype.replace_file = function(xhr_response) {
    var file_id = $.parseJSON(xhr_response)['file_id'];
    console.log(file_id);
    this.js_form[this.current.name] = String(file_id);
    this.upload_or_submit();
}

function process_file(handler) {
    var file = handler.current.files[0];
    var reader = new FileReader();
    reader.onload = function(event){  // When the file is loaded
        var data = event.target.result;
        setTimeout(function() {  // Perform asynchronously
            var base64 = window.btoa(data);
            var sha1 = hex_sha1(data);
            var url = '/file/' + sha1 + '/info';
            console.log('Checking if ' + sha1 + ' exists');
            $.ajax({url: url, complete: function(xhr) {  // Test if file exists
                if (xhr.status == 404) {
                    console.log('Uploading file for ' + sha1);
                    var form_json = JSON.stringify({b64data: base64});
                    var url = '/file/' + sha1;
                    $.ajax({url: url, type: 'PUT', complete: function(xhr) {
                        if (xhr.status == 200)
                            handler.replace_file(xhr.responseText);
                        else {
                            console.log('Error uploading file: ' + xhr.status);
                        }}, data: form_json});
                }
                else
                    handler.replace_file(xhr.responseText);
            }});
        }, 0);
    };
    reader.readAsBinaryString(file);
}
