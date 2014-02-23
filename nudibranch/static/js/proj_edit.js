function hfd(lhs, rhs) {
    var retval = $('<div>');
    var control = $('<div class="control-label">');
    if (lhs != '') {
        $(lhs).appendTo(control);
        control.appendTo(retval);
    }
    var group = $('<div class="controls">');
    $(rhs).appendTo(group);
    group.appendTo(retval);
    return retval;
}
function files_form(category, info, ids) {
    var lcn = null;
    var new_title = '<i class="icon-white icon-file"></i> New';
    if (category == 0) {
        var name = 'Build File';
        var path = build_file_path;
    }
    else if (category == 1) {
        var name = 'Execution File';
        var path = execution_file_path;
    }
    else {
        var name = 'Expected File';
        var path = expected_file_path;
        lcn = 'file_verifier';
        new_title = 'Define'
    }
    lcn = lcn || name.replace(' ', '_').toLowerCase();
    var retval = $('<div class="span4 well well-small"><h3>Select {0}s</h3>'
                   ._format(name));
    for (var i = 0; i < info.length; ++i) {
        var f = info[i];
        var checked = $.inArray(f['id'], ids) != -1 ? 'checked="checked"' : '';

        var lhs = '<span class="btn btn-danger btn-mini button-delete" \
data-name="{0}" data-url="{1}/{2}"><i class="icon-white icon-trash"></i> \
Delete</span>'._format(f['name'], path, f['id']);;

        if (category != 2) {
            lhs += '<a class="btn btn-info btn-mini" style="color: white" \
href="{0}/{1}/{2}" target="_blank"><i class="icon-white icon-search"></i> \
View</a>'._format(file_path, f['file_hex'], f['name'])
        }
        else {
            lhs += '<span class="btn btn-warning btn-mini" onclick=\
"$(\'#file_verifier_{0}\').dialog(\'open\');"><i class="icon-white \
icon-pencil"></i> Edit</span>'._format(f['id']);
        }

        hfd(lhs, ('<label class="checkbox"><input type="checkbox" ' +
                  'name="{0}_ids[]" value="{1}" {2}>  {3}</label>')
            ._format(lcn, f['id'], checked, f['name'])).appendTo(retval);
    }
    hfd('',
        ('<span class="btn btn-success" onclick="$(\'#{0}_new\')' +
         '.dialog(\'open\');">{2} {1}</span>')._format(lcn, name, new_title))
        .appendTo(retval);
    return retval;
}
function testable_div(info) {
    var div = $('<div id="testable_tab_{0}">'._format(info['id']));
    if (info['id'] == 'new') {
        var action = '/testable';
        var method = 'PUT';
        var tb_name = '';
    }
    else {
        var action = '/testable/{0}'._format(info['id']);
        var method = 'POST';
        var tb_name = info['name'];
    }
    var hidden = info['hidden'] ? 'checked="checked"' : '';
    var form = $(('<form class="form-horizontal" role="form" action="{0}"' +
                  ' onsubmit="return form_request(this, \'{1}\', true);"/>')
                 ._format(action, method));
    var row = $('<div class="row-fluid">');
    files_form(0, build_files, info['build_files']).appendTo(row);
    files_form(1, execution_files, info['execution_files']).appendTo(row);
    files_form(2, expected_files, info['expected_files']).appendTo(row);
    row.appendTo(form);
    hfd('<label for="testable_name_{0}">Testable Name</label>'
        ._format(info['id']),
        '<input type="text" id="testable_name_{0}" name="name" value="{1}">'
        ._format(info['id'], tb_name)).appendTo(form);
    hfd('<label for="make_target_{0}">Make Target</label>'
        ._format(info['id']),
        ('<input type="text" id="make_target_{0}" name="make_target" ' +
         'placeholder="do not run make" value="{1}">')
        ._format(info['id'], info['target'] || '')).appendTo(form);
    hfd('<label for="executable_{0}">Executable</label>'
        ._format(info['id']),
        ('<input type="text" id="executable_{0}" name="executable" ' +
         'value="{1}">')._format(info['id'], info['executable']))
        .appendTo(form);
    hfd('',
        '<label class="checkbox"><input type="checkbox" name="is_hidden" ' +
        'value="1" {0}> Hide results from students</label>'._format(hidden))
        .appendTo(form);
    if (info['id'] == 'new') {
        hfd('<input type="hidden" name="project_id" value="{0}"/>'
            ._format(proj_id),
            '<button class="btn btn-success" type="submit">' +
            'Add Testable</button>').appendTo(form);
    }
    else {
        hfd('',
            ('<button class="btn btn-warning" type="submit">Update {0}' +
             '</button><span class="btn btn-danger button-delete" ' +
             'data-name="{0}" data-url="/testable/{1}"><i class="icon-white ' +
             'icon-trash"></i> Delete {0}</span>')
            ._format(info['name'], info['id'])).appendTo(form);
    }
    form.appendTo(div);
    return div;
}
function add_testables(testable_data) {
    var tt = $("#testable_tab");
    var ul = tt.find('ul');
    for (var i = 0; i < testable_data.length; ++i) {
        var info = testable_data[i];
        ul.append('<li><a href="#testable_tab_{0}">{1}</a></li>'
                  ._format(info['id'], info['name']));
        testable_div(info).appendTo(tt);
    }
}
$(function() {
    add_testables(testables);

    $(".dialog").dialog({autoOpen: false, width: 400});
    $("#testable_tab").tabs();
    $(".button-delete").on("click", function(event) {
        var name = event.target.getAttribute("data-name");
        var url = event.target.getAttribute("data-url");
        if (confirm("Are you sure you want to delete " + name + "?")) {
            $.ajax({url: url, type: "delete", complete: handle_response});
        }
    });
    $(".toggle_tc_file").on("change", function(event) {
        var testable = event.target.getAttribute("data-testable");
        var tc = event.target.getAttribute("data-tc");
        var div = $("#testable_" + testable + "_" + tc + "_file_div");
        var input = $("#testable_" + testable + "_tc_output_filename_" + tc);
        if (event.target.value == "file") {
            div.show();
            input.removeAttr("disabled");
        }
        else {
            div.hide();
            input.attr("disabled", "disabled");
        }
    });
    $(".toggle_tc_expected").on("change", function(event) {
        var testable = event.target.getAttribute("data-testable");
        var tc = event.target.getAttribute("data-tc");
        var div = $("#testable_" + testable + "_" + tc + "_expected_div");
        var hidden = $("#testable_" + testable + "_tc_expected_id_" + tc);
        var input = $("#testable_" + testable + "_tc_expected_" + tc);
        if (event.target.value == "diff") {
            div.show();
            hidden.removeAttr("disabled");
            input.removeAttr("disabled");
        }
        else {
            div.hide();
            hidden.attr("disabled", "disabled");
            input.attr("disabled", "disabled");
        }
    });
    $("#requeue").on("click", function(event) {
        if (confirm("Are you sure you want to requeue all the latest submissions?")) {
            $.ajax({url: window.location.href, type: 'put', complete: handle_response});
        }
    });
});
