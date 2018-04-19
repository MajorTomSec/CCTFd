$('#submit-key').unbind('click');
$('#submit-key').click(function (e) {
    e.preventDefault();
    submitkey($('#chal-id').val(), $('#answer-input').val(), $('#nonce').val())
});

$('#limit_max_attempts').change(function() {
    if(this.checked) {
        $('#chal-attempts-group').show();
    } else {
        $('#chal-attempts-group').hide();
        $('#chal-attempts-input').val('');
    }
});

$("#answer-input").keyup(function(event){
    if(event.keyCode == 13){
        $("#submit-key").click();
    }
});

$(".input-field").bind({
    focus: function() {
        $(this).parent().addClass('input--filled' );
        $label = $(this).siblings(".input-label");
    },
    blur: function() {
        if ($(this).val() === '') {
            $(this).parent().removeClass('input--filled' );
            $label = $(this).siblings(".input-label");
            $label.removeClass('input--hide' );
        }
    }
});
