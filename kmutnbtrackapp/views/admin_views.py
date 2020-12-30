"""
Imports should be grouped in the following order:

1.Standard library imports.
2.Related third party imports.
3.Local application/library specific imports.
"""

import csv
import qrcode
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from django.contrib import messages
from django.core import management
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpResponseRedirect, HttpResponse
from django.utils.http import urlsafe_base64_decode
from django.shortcuts import redirect
from django.utils.encoding import force_bytes
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import Group, Permission

from kmutnbtrackapp.dashboard import *
from kmutnbtrackapp.views.help import *
from kmutnbtrackapp.views.help import tz


@superuser_login_required
def history_search(request, page=1):
    """Received from the client and searched for information from the server and then sent back to the client"""
    keyword = request.GET.get('keyword', '')
    start = request.GET.get('from', '')
    stop = request.GET.get('to', '')
    mode = request.GET.get('mode', '')
    histories, all_history = query_search(mode, keyword, start, stop, "normal")

    p = Paginator(all_history, 36)
    num_pages = p.num_pages
    shown_history = p.page(page)

    split_url = request.get_full_path().split("/")
    if page == 1:
        prev_url = None

        if num_pages != 1:
            split_url[-2] = "2"
            next_url = "/".join(split_url)
        else:
            next_url = None

    elif page == num_pages:
        split_url[-2] = str(num_pages - 1)
        prev_url = "/".join(split_url)

        next_url = None

    else:
        split_url[-2] = str(page - 1)
        prev_url = "/".join(split_url)

        split_url[-2] = str(page + 1)
        next_url = "/".join(split_url)
    return render(request, 'admin/history_search.html',
                  {'shown_history': shown_history,
                   'keyword': keyword,
                   'select_mode': mode,
                   'start': start,
                   'stop': stop,
                   'current_page_number': page,
                   'prev_url': prev_url,
                   'next_url': next_url,
                   })


@supervisor_login_required
def view_lab(request, lab_hash):
    this_lab = Lab.objects.get(hash=lab_hash)
    if not (request.user.is_superuser or request.user.groups.filter(name=this_lab.name).exists()):
        return render(request, 'Page/error.html', {"error_message": "Permission denied"})
    now_datetime = datetime.datetime.now(tz)
    midnight_time = now_datetime.replace(hour=23, minute=59, second=59, microsecond=0)
    current_people = History.objects.filter(lab=this_lab,
                                            checkout__gte=now_datetime,
                                            checkout__lte=midnight_time)
    if request.method == "POST" and request.POST.get('confirm', '') == "ยืนยัน":
        for person in current_people:
            out_local_time = datetime.datetime.now(tz)
            person.checkout = out_local_time
            person.save()
        messages.info(request, 'All the people in %s has been cleared successfully' % this_lab.name)
        return HttpResponseRedirect('/admin/kmutnbtrackapp/lab/')
    elif request.method == "POST" and request.POST.get('confirm', '') != "ยืนยัน":
        return render(request, 'admin/notify_confirm.html', {'clear_lab': True, 'this_lab': this_lab, 'fail': True})
    return render(request, 'admin/view_lab.html', {'this_lab': this_lab, 'shown_history': current_people})


@superuser_login_required
def export_normal_csv(request):
    """export file csv log to user"""
    mode = request.GET.get('mode', '')
    keyword = request.GET.get('keyword', '')
    start = request.GET.get('from', '')
    stop = request.GET.get('to', '')
    histories, all_history = query_search(mode, keyword, start, stop, "normal")
    response = HttpResponse(content_type='text/csv')
    writer = csv.writer(response)
    writer.writerow(['Student ID', 'Person Name', 'Phone number', 'Lab Name', 'Check in time', 'Check out time'])
    for user in all_history:
        user = list(user)
        user[4] = user[4].astimezone(tz)
        user[5] = user[5].astimezone(tz)
        writer.writerow(user)
    response['Content-Disposition'] = 'attachment; filename="file_log.csv"'
    return response


@superuser_login_required
def risk_people_search(request):
    """Received from the client filter data and sent back to client"""
    risk_people_data = "EMPTY"
    keyword = ""
    mode = ""
    if request.GET:  # if request has parameter
        mode = request.GET.get('mode', '')
        keyword = request.GET.get('keyword', '')
        risk_people_data, risk_people_notify = filter_risk_user(mode, keyword)

    return render(request, 'admin/risk_people_search.html',
                  {'shown_history': risk_people_data,
                   'keyword': keyword, 'select_mode': mode,
                   })


def generate_qr_code(request, lab_hash):
    lab_name = Lab.objects.get(hash=lab_hash).name
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=20,
        border=0,
    )
    qr.add_data(f"https://labtrack.cony.codes/lab/{lab_hash}/")
    qr.make()
    img_qr = qr.make_image()

    img_frame = Image.open("kmutnbtrackapp/static/qrcode_src/QR_frame.png", 'r')

    pos = (80 + 30, 295 + 19)
    img_frame.paste(img_qr, pos)

    drawer = ImageDraw.Draw(img_frame)

    font_size = 66
    font = ImageFont.truetype("kmutnbtrackapp/static/qrcode_src/GOTHICB.ttf", font_size)
    ascent, descent = font.getmetrics()
    (width, baseline), (offset_x, offset_y) = font.font.getsize(lab_name)

    if len(lab_name) > 30:
        drawer.text((100, 190), "Lab name too long!!!", (128, 0, 0), font=font)

    elif len(lab_name) > 14:  # long name -> reduce font size
        while width >= 580:
            font_size -= 1
            font = ImageFont.truetype("kmutnbtrackapp/static/qrcode_src/GOTHICB.ttf", font_size)
            ascent, descent = font.getmetrics()
            (width, baseline), (offset_x, offset_y) = font.font.getsize(lab_name)

    drawer.text((400 - int((width + 74) / 2) + 74, 220 - ascent), lab_name, (0, 0, 0), font=font)

    flag_img = Image.open("kmutnbtrackapp/static/qrcode_src/maps-and-flags.png", 'r')
    flag_img = flag_img.resize((74, 74), resample=Image.LANCZOS)
    pos = (int(400 - (width + 74) / 2 - 3),
           int(220 - ascent + offset_y + (ascent - offset_y) / 2 - 74 / 2))
    img_frame.paste(flag_img, pos, mask=flag_img.split()[1])

    img_frame.save(f'media/{lab_name}_qrcode.png', "PNG", quality=100)
    with open(f'media/{lab_name}_qrcode.png', "rb") as f:
        response = HttpResponse(f.read(), content_type="image/png")
        response['Content-Disposition'] = 'inline; filename=' + f'media/{lab_name}_qrcode.png'
        return response


@superuser_login_required
def export_risk_csv(request):
    """export file risk user csv log to user"""
    mode = request.GET.get('mode', '')
    keyword = request.GET.get('keyword', '')
    if keyword != "":
        risk_people_data, not_use = filter_risk_user(mode, keyword)
        response = HttpResponse(content_type='text/csv')
        writer = csv.writer(response)
        writer.writerow(
            ['Student ID', 'Person Name', 'Phone number', 'Lab Name', 'Check in time', 'Check out time'])
        for user in risk_people_data:
            user = list(user)
            user[4] = user[4].astimezone(tz)
            user[5] = user[5].astimezone(tz)
            writer.writerow(user)
        response['Content-Disposition'] = 'attachment; filename="Risk Log.csv"'
        return response
    else:
        return redirect(risk_people_search)


@superuser_login_required
def notify_confirm(request, where):
    lab_hash = request.GET.get('lab_hash', '')
    if not lab_hash == '':
        this_lab = Lab.objects.get(hash=lab_hash)
    if where == 'risk_people_search':
        mode = request.GET.get('mode', '')
        keyword = request.GET.get('keyword', '')
        if keyword != "":
            return render(request, 'admin/notify_confirm.html', {'mode': mode,
                                                                 'keyword': keyword,
                                                                 'send_email': True,
                                                                 })
        else:
            return redirect(risk_people_search)
    elif where == 'clear_lab':
        return render(request, 'admin/notify_confirm.html', {'clear_lab': True, 'this_lab': this_lab})


@superuser_login_required
def notify_user(request, mode, keyword):
    confirm = request.POST.get('confirm', '')
    if request.method == "POST" and confirm == "ยืนยัน":
        risk_people_data, risk_people_notify = filter_risk_user(mode, keyword)
        # remove duplicate user'info
        user_info = []
        for each_list in risk_people_notify:
            std_id = each_list[0]
            name = each_list[1]
            email = each_list[2]
            temp_list = [std_id, name, email]
            for each in risk_people_notify:
                if each[1] == name and each[3] not in temp_list:
                    temp_list.append(each[3])
            user_info.append(tuple(temp_list))
        risk_people_notify = set(user_info)

        user_data = {}
        user_email = []
        for each_user in risk_people_notify:
            student_id = each_user[0]
            first_last_name = each_user[1]
            each_user_email = each_user[2]
            if each_user_email != '':
                user_email.append(each_user_email)
                lab_name = ''
                for each_lab in each_user[3:]:
                    lab_name += str(each_lab) + ', '
                lab_name = lab_name[:-2]
                user_data[each_user_email] = {'student_id': student_id,
                                              'first_last_name': first_last_name,
                                              'user_email': each_user_email,
                                              'lab_name': lab_name}
        subject = 'แจ้งเตือนกลุ่มผู้มีความเสี่ยงติดเชื้อ COVID-19'
        email = EmailMessage(subject, to=user_email)
        email.template_id = 'notify-labtrack'
        email.merge_data = user_data
        email.send()

        return render(request, 'admin/notify_status.html',
                      {'notify_status': True,
                       })
    else:
        return render(request, 'admin/notify_confirm.html', {'mode': mode,
                                                             'keyword': keyword,
                                                             'send_email': True,
                                                             'fail': True,
                                                             })


@supervisor_login_required
def call_dashboard(request):
    """load metadata check update and format it before send data to dashboard"""

    """load and manage metadata"""
    meta_data = get_data_metadata()
    dataset = query_search('', '', meta_data["latest time"], datetime.datetime.now(tz), "dashboard")
    for user in dataset:
        try:
            if str(user.lab) in meta_data['lab']:
                if (str(user.checkout.year) + "/" + str(user.checkout.month) + "/" + str(user.checkout.day)) in \
                        meta_data['lab'][str(user.lab)]:
                    meta_data['lab'][str(user.lab)][
                        str(user.checkout.year) + "/" + str(user.checkout.month) + "/" + str(user.checkout.day)] += 1
                else:
                    meta_data['lab'][str(user.lab)][
                        str(user.checkout.year) + "/" + str(user.checkout.month) + "/" + str(user.checkout.day)] = 1
            else:
                meta_data['lab'][str(user.lab)] = {}
                meta_data['lab'][str(user.lab)][
                    str(user.checkout.year) + "/" + str(user.checkout.month) + "/" + str(user.checkout.day)] = 1
        except AttributeError:
            pass
    meta_data["latest time"] = datetime.datetime.now(tz).strftime('%Y-%m-%dT%H:%M:%S.%f')
    write_metadata(meta_data)
    """prepare data before sent to template"""
    pie_data = prepare_pie_data(meta_data)
    liner_data = prepare_liner_data(meta_data)
    histrogram_data = prepare_single_liner_data(meta_data)
    room_stauts = prepare_room_status(Lab.objects.values('name', 'max_number_of_people'), History.objects)
    return render(request, 'admin/dashboard.html', {
        'pie_data': json.dumps(pie_data),
        'liner_data': json.dumps(liner_data),
        'histrogram_dump': json.dumps(histrogram_data),
        "histrogram_data": histrogram_data,
        "room_status": json.dumps(room_stauts),
    })


@superuser_login_required
def backup(request):
    """ manually back up database """

    # call command python manage.py dbbackup
    management.call_command('dbbackup')

    messages.info(request, 'Database has been backed up successfully!')
    return HttpResponseRedirect('/admin')


def auth_head(request, uid_b64, token):
    try:
        uid = urlsafe_base64_decode(uid_b64).decode()
        user = get_user_model()._default_manager.get(pk=uid)
    except(TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and default_token_generator.check_token(user, token):
        new_lab_data = LabPending.objects.get(staff_user=user)
        if new_lab_data.head_email is None:
            auth_staff(request, uid_b64, token)
            return HttpResponseRedirect('/admin/')
        else:
            current_site = get_current_site(request)
            mail_subject = "เราได้รับคำขอสร้างแลป " + new_lab_data.name
            lab_head = {new_lab_data.head_email: {'first_name': new_lab_data.lab_head_first_name,
                                                  'last_name': new_lab_data.lab_head_last_name,
                                                  'staff_first_name': user.first_name, 'staff_last_name': user.last_name,
                                                  'lab_name': new_lab_data.name,
                                                  'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                                                  'token': default_token_generator.make_token(user),
                                                  'domain': current_site.domain}}
            email = EmailMessage(mail_subject, to=[new_lab_data.head_email])
            email.template_id = 'lab-send-head'
            email.merge_data = lab_head
            email.send()
            success_message = "แลป " + new_lab_data.name + " ได้รับการยืนยันแล้ว"
            return render(request, 'Page/success.html', {'success_message': success_message})
    else:
        return HttpResponse('ลิ้งค์ยินยันผิดพลาด ให้รีบแจ้งผู้ส่งคำขอโดยด่วน')


def auth_staff(request, uid_b64, token):
    try:
        uid = urlsafe_base64_decode(uid_b64).decode()
        user = get_user_model()._default_manager.get(pk=uid)
    except(TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.is_staff = True
        permission = Permission.objects.get(name="Can view lab")
        user.user_permissions.add(permission)
        user.save()
        Person.objects.create(user=user, first_name=user.first_name, last_name=user.last_name, is_student=False)
        new_lab_data = LabPending.objects.get(staff_user=user)
        Lab.objects.create(name=new_lab_data.name, max_number_of_people=new_lab_data.max)
        new_group = Group.objects.create(name=new_lab_data.name)
        new_group.user_set.add(user)
        new_lab_data.delete()

        mail_subject = new_lab_data.name + " ได้รับการยืนยีนแล้ว"
        lab_activated = {user.email: {'username': user.username, 'lab_name': new_lab_data.name}}
        email = EmailMessage(mail_subject, to=[user.email])
        email.template_id = 'lab-create-confirm'
        email.merge_data = lab_activated
        email.send()
        messages.info(request, '%s has been activated successfully' % new_lab_data.name)
        return HttpResponseRedirect('/admin/')
    else:
        return HttpResponse('ลิ้งค์ยินยันผิดพลาด ให้รีบแจ้งผู้ส่งคำขอโดยด่วน')
