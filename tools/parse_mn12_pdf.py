"""Build the MN12 health-check import dataset from MN12_Kham_Suc_Khoe_2026.pdf.

Rows are transcribed verbatim from the PDF table (127 children, TT 1..127).
Writes scripts/parsed_children_mn12.json in the shape import_health_check_firefox.py expects.
"""

import json
import re
from typing import Dict, List, Optional

SCHOOL_NAME = "Trường Mầm non 12"
SCHOOL_ADDRESS = "19-21-23-25 Đoàn Như Hài, Phường Xóm Chiếu"
SCHOOL_WARD = "Phường Xóm Chiếu"

# TT, name, gender, dob, cccd, bhyt, address, mother, mother_cccd, phone, lop
ROWS = [
    (1, "Đặng Nguyễn Minh Anh", "Nữ", "25/07/2024", "082324005642", "8224347809", "72 Nguyễn Trường Tộ P.Xóm Chiếu", "Nguyễn Thị Kim Oanh", "082186016445", "0983738716", "Thỏ trắng"),
    (2, "Nguyễn An Chi", "Nữ", "08/04/2024", "079324008787", "7940311137", "262/129 Đoàn Văn Bơ P. Khánh Hội", "Hồ Thị Cẩm Thu", "083196003033", "0366803807", "Thỏ trắng"),
    (3, "Nguyễn Lương Khả Di", "Nữ", "06/04/2024", "079324005914", "7940306824", "122/27/33a Tôn Đản P. Khánh Hội", "Lương Hạnh Phương Uyên", "079197010042", "0919675872", "Thỏ trắng"),
    (4, "Lê Nguyễn Khánh Di", "Nữ", "02/06/2024", "079324015255", "7940341752", "198 Đường số 48 P.Vĩnh Hội", "Nguyễn Thu Phương", "001189015102", "0935605239", "Thỏ trắng"),
    (5, "Trần Minh Hòa", "Nam", "31/01/2024", "079224001696", "7940269388", "156/1 Hoàng Diệu P. Khánh Hội", "Trần Thị Kim Trang", "079183017733", "0936458704", "Thỏ trắng"),
    (6, "Mai Hoàng Huy", "Nam", "06/07/2024", "079224017398", "7940349126", "137/41 Bến Vân Đồn P.Khánh Hội", "Trương Nhựt Yến Nhi", "079306003301", "0774165915", "Thỏ trắng"),
    (7, "Huỳnh Gia Khang", "Nam", "14/08/2024", "079224022573", "7940406422", "48 Hoàng Diệu P. Xóm Chiếu", "Nguyễn Thị Hạnh", "049192008994", "0907121003", "Thỏ trắng"),
    (8, "Nguyễn Đăng Khôi", "Nam", "10/10/2024", "079224030842", "7940423950", "141 Lô I Đoàn Văn Bơ P. Khánh Hội", "Mai Thị Ngọc Trâm", "079304004317", "0969383902", "Thỏ trắng"),
    (9, "Huỳnh Phan Hà Linh", "Nữ", "15/08/2024", "079324022097", "7940406423", "140/16 Lê Quốc Hưng P.Xóm Chiếu", "Phan Thị Hà", "038188014318", "0909494043", "Thỏ trắng"),
    (10, "Phạm Thiên Long", "Nam", "16/06/2024", "079224005125", "", "15/44 Đoàn Như Hài P.Xóm Chiếu", "Mai Thị Mừng", "034193005814", "0385426269", "Thỏ trắng"),
    (11, "Nguyễn Bảo Luân", "Nam", "29/06/2024", "079224020875", "7940366988", "148/12/20/48A Tôn Đản P. Khánh Hội", "Nguyễn Thị Màu", "091191004801", "0769975651", "Thỏ trắng"),
    (12, "Tô Nhật Minh", "Nam", "03/07/2024", "038224015693", "", "30 Đoàn Văn Bơ P. Khánh Hội", "Hồ Thị Cúc", "038183042890", "0328124655", "Thỏ trắng"),
    (13, "Nguyễn Đông Nhi", "Nữ", "04/07/2024", "079324016833", "7940350782", "201 Hoàng Diệu P.Khánh Hội", "Lê Thị Hạnh Huyền", "068190000443", "0915084548", "Thỏ trắng"),
    (14, "Nguyễn Như Mẫn Nhi", "Nữ", "18/02/2024", "079324003449", "7940277604", "500/37/2 Đoàn Văn Bơ P.Khánh Hội", "Phạm Thị Duy Phương", "079182002873", "0988105440", "Thỏ trắng"),
    (15, "Đỗ Nguyễn An Nhiên", "Nữ", "24/07/2024", "079324018182", "7940358359", "156/1 Hoàng Diệu P.Khánh Hội", "Nguyễn Thị Hồng Sương", "056192000751", "0932491548", "Thỏ trắng"),
    (16, "Phạm Lê Minh Quân", "Nam", "27/01/2024", "079224005391", "7940286983", "66 Đường số 41 P.Khánh Hội", "Lê Thị Ngọc Giàu", "079194014280", "0794465945", "Thỏ trắng"),
    (17, "Nguyễn Ngọc Linh San", "Nữ", "01/04/2024", "079324020542", "7940420117", "500/37/8 Đoàn văn Bơ P. Khánh Hội", "Nguyễn Thị Ngọc Châu", "083189014862", "0975544843", "Thỏ trắng"),
    (18, "Dương Viết Vĩ", "Nam", "21/05/2024", "079224020788", "7940367310", "243/64 Tôn Thất Thuyết P.Vĩnh Hội", "Nguyễn Ngọc Yến Như", "079300008299", "0901489376", "Thỏ trắng"),
    (19, "Nguyễn Hoàng Phúc Khang", "Nam", "14/11/2024", "079224040256", "7940472955", "171/3 Tôn Thất Thuyết P.Khánh Hội", "Trần Thị Phúc", "040198021792", "0852197284", "Thỏ trắng"),
    (20, "Trần Vĩnh Hy", "Nam", "28/11/2024", "079224036163", "7940451457", "151H KTT Hoàng Diệu P.Khánh Hội", "Võ Nhựt Uyển", "079198008343", "0938072861", "Thỏ trắng"),
    (21, "Nguyễn Hà Trúc My", "Nữ", "30/09/2024", "079324030290", "7940431400", "322/7 Nguyễn Tất Thành P.Xóm Chiếu", "Hà Vũ Xuân Nhi", "079304008465", "0988737337", "Thỏ trắng"),
    (22, "Nguyễn Hoàng Trọng Khôi", "Nam", "05/02/2024", "079224002810", "7940275612", "71 Hoàng Diệu P.Khánh Hội", "Hoàng Ngọc Quỳnh Như", "079192018028", "0908357240", "Thỏ trắng"),
    (23, "Phạm Hồng Đăng", "Nam", "25/12/2024", "079224041315", "7940491949", "484 Lô Q Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Thị Bích Ngọc", "092191000960", "0903343386", "Thỏ trắng"),
    (24, "Nguyễn Huy Anh", "Nam", "17/09/2023", "079223036920", "7940206571", "109D/96/28A Bến Vân Đồn P.Khánh Hội", "Nguyễn Thị Huyện Trân", "079192008440", "0839396909", "Sóc nâu"),
    (25, "Cao Chi Bảo", "Nam", "20/05/2023", "079223015304", "7940146521", "156/3 Hoàng Diệu P.Xóm Chiếu", "Nguyễn Phạm Triều My", "079195022512", "0938577317", "Sóc nâu"),
    (26, "Phạm Phi Di", "Nữ", "30/05/2023", "079323024259", "7940155015", "Lô L332 KTT Hoàng Diệu P.Khánh Hội", "Phạm Thị Thanh", "058192008923", "0786559768", "Sóc nâu"),
    (27, "Dương Tiến Đức", "Nam", "29/11/2023", "079223046897", "7940243189", "B416/50A Đoàn Văn Bơ P.Xóm Chiếu", "Ân Thị Thơ", "040191008731", "0772672616", "Sóc nâu"),
    (28, "Hoàng Lê Chí Hào", "Nam", "31/08/2023", "079223035207", "7940197769", "874/5 Đoàn Văn Bơ P.Xóm Chiếu", "Lê Mỹ Nhàn", "079197005618", "0986544435", "Sóc nâu"),
    (29, "Hồ Vĩnh Hy", "Nam", "04/05/2023", "079223011291", "7940145497", "538/78/6 Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Thị Thu Phượng", "051192014995", "0938477598", "Sóc nâu"),
    (30, "Tô Thành Kiệt", "Nam", "09/12/2023", "079223049781", "7940259357", "150/33 Bến Vân Đồn P.Khánh Hội", "Trần Ngọc Thu", "079191017434", "0938846136", "Sóc nâu"),
    (31, "Đoàn Trần Thiên Kim", "Nữ", "09/04/2023", "079323007464", "7940134271", "T38 Cư Xá Vĩnh Hội P.Khánh Hội", "Trần Thị Phương Duy", "079197006501", "0937881902", "Sóc nâu"),
    (32, "Hồ Thiên Kim", "Nữ", "21/08/2023", "079323039776", "7940192144", "65/22 Đoàn Như Hài P.Xóm Chiếu", "Hồ Nguyễn Ngọc Trang", "079304025076", "0902319251", "Sóc nâu"),
    (33, "Đoàn Huỳnh Mộc Lam", "Nữ", "28/08/2023", "079323039728", "7940191038", "204/19 Lê Quốc Hưng P. Xóm Chiếu", "Huỳnh Thị Bích Nga", "080188015228", "0932610937", "Sóc nâu"),
    (34, "Nguyễn Ngọc Phương Linh", "Nữ", "28/11/2023", "079323053072", "7940243004", "57 Cù Lao Nguyễn Kiệu P. Vĩnh Hội", "Lý Đinh Phương Trang", "000938269018", "0938269018", "Sóc nâu"),
    (35, "Phạm Nhật Minh", "Nam", "25/09/2023", "079223037437", "7940206384", "65/25 Đoàn Như Hài P.Xóm Chiếu", "Lê Gia Huệ", "079302007319", "0987109116", "Sóc nâu"),
    (36, "Trần An Nhi", "Nữ", "24/02/2023", "079323004330", "7940114817", "352/16A Nguyễn Tất Thành P.Xóm Chiếu", "Lê Thị Mỹ Nhàn", "079192033255", "0865034360", "Sóc nâu"),
    (37, "Nguyễn Ngọc Tuệ Nhi", "Nữ", "09/10/2023", "079323046321", "7940213582", "168/6 Đoàn văn Bơ P.Khánh Hội", "Châu Kiều Bảo Ngọc", "079192014708", "0902387793", "Sóc nâu"),
    (38, "Võ Phương Quỳnh", "Nữ", "11/09/2024", "079324023332", "7940390734", "41/B6 Lê Văn Linh P.Xóm Chiếu", "Nguyễn Thị Phương Khanh", "079191008773", "0379516087", "Sóc nâu"),
    (39, "Mai Hạo Thiên", "Nam", "20/02/2023", "079223006581", "7940123454", "H162 KTT Hoàng Diệu P.Khánh Hội", "Trần Thị Kim Ngân", "079198013579", "0906783843", "Sóc nâu"),
    (40, "Nguyễn Trường Thịnh", "Nam", "31/10/2023", "079223047081", "7940241896", "90 Lê Văn Linh P.Xóm Chiếu", "Nguyễn Thị Ngọc Vẹn", "079187006419", "0933671987", "Sóc nâu"),
    (41, "Huỳnh Nguyễn Bảo Trâm", "Nữ", "08/04/2023", "079323009820", "7940141913", "148/12/50/23 Tôn Đản P. Khánh Hội", "Nguyễn Ngọc Thùy Trang", "079198022626", "0933993353", "Sóc nâu"),
    (42, "Lê Nguyễn Thùy Vân", "Nữ", "21/05/2023", "079323023172", "7940199411", "164/23 Lê Quốc Hưng P.Xóm Chiếu", "Nguyễn Trương Thị Hương Huyền", "079198011375", "0798728905", "Sóc nâu"),
    (43, "Nguyễn Ngọc Khánh Vân", "Nữ", "03/08/2024", "079324019244", "7940364527", "188/37 Đoàn Văn Bơ P.Khánh Hội", "Lê Trần Thiên Kim", "079196012617", "0937430996", "Sóc nâu"),
    (44, "Nguyễn Duy Việt", "Nam", "22/09/2023", "079223040107", "", "Căn hộ 504 Nguyễn Tất Thành P. Xóm Chiếu", "Nguyễn Trần Tường Vy", "079301000353", "0931311941", "Sóc nâu"),
    (45, "Trương Ngọc Tâm Anh", "Nữ", "27/08/2024", "079324022030", "7940422080", "1491/28 Phạm Thế Hiển P.Bình Đông", "Trần Ngọc Thảo", "079187035351", "0937111087", "Sóc nâu"),
    (46, "Trần Ngọc Thanh Phương", "Nữ", "30/07/2024", "079324019389", "7940367309", "103 Lô B1 Chung cư Phường 3 P.Vĩnh Hội", "Nguyễn Ngọc Bích Vy", "079195019568", "0902379158", "Sóc nâu"),
    (47, "Võ Chí Khang", "Nam", "14/07/2024", "079224018796", "7940355311", "198/44 Đoàn Văn Bơ P.Khánh Hội", "Trần Hồng Nghi", "079303019239", "0773068028", "Sóc nâu"),
    (48, "Nguyễn Thế Bảo Đăng", "Nam", "04/05/2024", "079224017588", "7940468276", "243/31/16 Tôn Đản P.Khánh Hội", "Đỗ Thị Ngọc Dung", "083197000005", "0933373868", "Sóc nâu"),
    (49, "Cao Hạo Lâm", "Nam", "16/09/2024", "079224026235", "7940398631", "42/45 Hoàng Diệu P.Xóm Chiếu", "Hứa Phạm Hoàng Yến", "079195002084", "0901116437", "Sóc nâu"),
    (50, "Tiêu Yến Nhi", "Nữ", "29/11/2023", "079323055797", "7940253927", "129F/123/128B/4A Bến Vân Đồn P. Khánh Hội", "Trương Thị Mỹ Phượng", "072189009490", "0703032434", "Sóc nâu"),
    (51, "Đinh Nguyễn Ngọc Trinh", "Nữ", "23/02/2023", "079323005054", "7940118338", "1886/17 Huỳnh Tấn Phát Xã Nhà Bè", "Nguyễn Thị Huệ", "087188011628", "0366362343", "Sóc nâu"),
    (52, "Đỗ Khánh An", "Nữ", "04/10/2023", "066323012735", "6624793562", "E50/4 Ấp 13 X.Bình Hưng", "Trương Thị Mỹ Hạnh", "051185014115", "0906780485", "Họa Mi"),
    (53, "Nguyễn Khánh An", "Nữ", "05/09/2024", "079324023448", "7940406597", "43/5 Đoàn Như Hài P.Xóm Chiếu", "Nguyễn Thị Thanh Hằng", "079188034004", "0936506510", "Họa Mi"),
    (54, "Thái Nhật Hạ", "Nữ", "02/08/2023", "079323039579", "7940190300", "41/40 Lê Văn Linh P. Xóm Chiếu", "Huỳnh Thị Thanh thủy", "079300012180", "0386123058", "Họa Mi"),
    (55, "Trần Nhã An Hiên", "Nữ", "11/02/2023", "079323005044", "7940119608", "B205-01 Chung cư Lê Thành P.An Lạc", "Phan Thị Liễu Châu", "084190000169", "0977267296", "Họa Mi"),
    (56, "Nguyễn Quang Huy", "Nam", "12/05/2024", "079224011393", "7940320844", "266/67 Tôn Đản P.Khánh Hội", "Nguyễn Thị Thùy Trang", "052192009460", "0339024124", "Họa Mi"),
    (57, "Huỳnh Quốc Bảo Khiêm", "Nam", "08/07/2023", "089223016607", "8926018100", "134/12 Đoàn Văn Bơ P. Khánh Hội", "Tô Thị Mỹ Trinh", "089199012711", "0927141519", "Họa Mi"),
    (58, "Trần Lê Hoàng Khôi", "Nam", "15/05/2023", "089223004327", "8925990283", "1/8 Hoàng Diệu P.Xóm Chiếu", "Lê Thị Bé Ba", "089188017499", "0945663885", "Họa Mi"),
    (59, "Nguyễn Ngọc Thiên Kim", "Nữ", "07/11/2024", "079324031288", "7940437428", "30/48 Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Thị Kim Trang", "079194007113", "0909368194", "Họa Mi"),
    (60, "Lê Hạo Minh", "Nam", "26/09/2024", "079224031436", "7940430233", "336 Lô C2 Chung cư phường 6 P.Khánh Hội", "Nguyễn Lâm Ni", "052192011710", "0904759184", "Họa Mi"),
    (61, "Nguyễn Ngọc Bảo Ngân", "Nữ", "10/05/2023", "079323011425", "7940145339", "43/11A Đoàn Văn Bơ P.Xóm Chiếu", "Nguyễn Ngọc Châu", "079192002586", "0767122171", "Họa Mi"),
    (62, "Phạm Khôi Nguyên", "Nam", "31/07/2023", "079223031155", "7940184903", "102 Chung cư Đoàn Văn Bơ P.Xóm Chiếu", "Nguyễn Thị Mộng Huyền", "075195010387", "0398820249", "Họa Mi"),
    (63, "Lưu Cát Ninh", "Nam", "24/05/2023", "079223018821", "7940161917", "121/18 Trần Bình Trọng P.Chợ Quán", "Lương Quế Linh", "079182035475", "0903528289", "Họa Mi"),
    (64, "Lê Nguyễn Ngọc Thư", "Nữ", "30/09/2023", "066323013057", "6624791509", "128/23 Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Thị Thu Hiền", "051184009657", "0376690896", "Họa Mi"),
    (65, "Nguyễn Ngọc Đan Thư", "Nữ", "16/02/2023", "079323003288", "7940111390", "158/46C Đoàn Văn Bơ P.Khánh Hội", "Trầm Thị Tuyết Anh", "079193027849", "0933548073", "Họa Mi"),
    (66, "Nguyễn Trang Trân", "Nữ", "06/05/2024", "079324012416", "7940328626", "52 Hoàng Diệu P.Xóm Chiếu", "Cao Thị Bích Phượng", "079182007896", "0907168961", "Họa Mi"),
    (67, "Bùi Minh Triết", "Nam", "13/11/2023", "079223046426", "7940238646", "303/18/10 Bến Vân Đồn P.Vĩnh Hội", "Trần Thị Nga", "031191008858", "0393539750", "Họa Mi"),
    (68, "Nguyễn Minh Triết", "Nam", "20/02/2023", "079223005273", "7940117972", "20 Đường số 11 P.Hiệp Bình", "Trương Hoàng Quỳnh Như", "079185018759", "0935038686", "Họa Mi"),
    (69, "Hồ Mai Uyên", "Nữ", "08/11/2023", "079323053842", "7940246148", "158/207 Đoàn văn Bơ P. Khánh Hội", "Nguyễn Thị Ngọc Phương", "079302011822", "0777951338", "Họa Mi"),
    (70, "Lê Ngọc An Vi", "Nữ", "21/05/2023", "079323022727", "7940146989", "243/31/14A Tôn Đản P.Khánh Hội", "Lê Mỹ Kym Hằng", "079195027782", "0839331919", "Họa Mi"),
    (71, "Nguyễn Ngọc Khánh Vy", "Nữ", "31/08/2023", "079323040420", "7940194501", "267/25 Đoàn Văn Bơ P. Xóm Chiếu", "Đặng Thị Thu", "037192001618", "0345744312", "Họa Mi"),
    (72, "Phạm Nhật Minh Hoàng", "Nam", "03/08/2023", "044223004683", "4421318141", "Căn hộ số B22.11 C/cư D-Aqua Bình Đông", "Lê Nhật Quỳnh", "044192002237", "0973181121", "Họa Mi"),
    (73, "Vũ Ngọc Ánh", "Nữ", "15/12/2023", "037323008251", "", "267/25 Đoàn Văn Bơ", "Đặng Thị Huệ", "037177001085", "0981682367", "Họa Mi"),
    (74, "Huỳnh Minh Khang", "Nam", "10/09/2023", "079223033031", "7940192290", "218H Lầu 4 Trần Hưng Đạo", "Huỳnh Thanh Lâm", "079194008784", "0788883020", "Họa Mi"),
    (75, "Nguyễn Trọng Doanh", "Nam", "08/12/2023", "079223049333", "7940249964", "287/19/5 Chu Văn An", "Huỳnh Ngọc Thảo Ly", "079192008690", "0932608626", "Họa Mi"),
    (76, "Châu Chí Uy", "Nam", "08/12/2023", "079223048748", "7940248316", "39-39B Cao ốc The Tresor TS1 14.15 Bến Vân Đồn", "Nguyễn Thị Nhung", "040193037150", "0988937766", "Họa Mi"),
    (77, "Đinh Ngọc Diệu Linh", "Nữ", "23/03/2023", "044323001439", "4421310200", "72-74 Nguyễn Tất Thành P. Xóm Chiếu", "Cao Thị Hằng", "044302001602", "0386815240", "Họa Mi"),
    (78, "Phan Hoàng Minh", "Nam", "26/10/2023", "079223050079", "7940253119", "324/5A Tôn Thất Thuyết P.Vĩnh Hội", "Nguyễn Thùy Dương", "037091008175", "0776699255", "Họa Mi"),
    (79, "Nguyễn Ngô Vinh", "Nam", "10/01/2023", "079223000384", "7940095437", "170/10A Bến Vân Đồn P.Khánh Hội", "Ngô Thục Uyên", "079191008136", "0904894248", "Họa Mi"),
    (80, "Huỳnh Thanh An", "Nam", "17/04/2022", "079222029725", "7940014003", "158/199 Đoàn Văn Bơ P.Khánh Hội", "Trần Kim Tuyến", "079303032992", "0767484707", "Mầm"),
    (81, "Đặng Trần Thiên An", "Nữ", "19/01/2022", "079322006328", "7939871595", "990W9 Đoàn Văn Bơ P.Khánh Hội", "Trần Thị Thu Hiền", "079191019472", "0902772315", "Mầm"),
    (82, "Trần Đặng Tâm Đạt", "Nam", "30/09/2022", "079222015846", "7940055711", "150/7 Đoàn Văn Bơ P.Khánh Hội", "Đặng Thị Huệ", "079184005584", "0902742852", "Mầm"),
    (83, "Trương Ngọc Thiên Di", "Nữ", "02/07/2022", "079322020741", "7940067685", "80 Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Ngọc Anh Thư", "079192002210", "0909980778", "Mầm"),
    (84, "Trần Minh Huy", "Nam", "02/12/2022", "079222025861", "7940091794", "129 Đoàn Văn Bơ P.Xóm Chiếu", "Nguyễn Trần Ngọc Châu", "079197036931", "0934129120", "Mầm"),
    (85, "Phạm Đức Khang", "Nam", "28/02/2022", "079222008731", "7939875352", "120/12 Lê Quốc Hưng P. Xóm Chiếu", "Đỗ Thị Bích Ngân", "079082032040", "0902652225", "Mầm"),
    (86, "Lê Ngọc Gia Khánh", "Nam", "12/02/2022", "017222000610", "1721122530", "Số 1/8 Hoàng Diệu P.Xóm Chiếu", "Bùi Thị hương Dịu", "017193008240", "0392307465", "Mầm"),
    (87, "Nguyễn Bảo Ngọc", "Nữ", "03/02/2022", "091322003019", "9124311395", "135 Lê Văn Linh P. Xóm Chiếu", "Đặng Thị Hạnh", "051192003880", "0988160244", "Mầm"),
    (88, "Mai Thành Nhân", "Nam", "17/02/2022", "079222006143", "7939872671", "120/29 Lê Quốc Hưng P.Xóm Chiếu", "Lê Thị Cẩm Tiên", "082196008947", "0974446497", "Mầm"),
    (89, "Trần Hoàng Trung Nhân", "Nam", "22/08/2022", "079222011770", "7940038925", "68/10 Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Thị Ngọc Hằng", "079196008098", "0968057443", "Mầm"),
    (90, "Lê Bảo Phúc", "Nam", "03/02/2022", "079222002573", "7939854543", "267/49 Đoàn Văn Bơ P. Xóm Chiếu", "Đặng Ngọc Lan", "079188006563", "0702057381", "Mầm"),
    (91, "Nguyễn Ngọc Phúc", "Nữ", "18/05/2022", "079322003848", "7940018876", "90 Lê Văn Linh P. Xóm Chiếu", "Nguyễn Thị Ngọc Vẹn", "079187006419", "0933671987", "Mầm"),
    (92, "Nguyễn Khánh Thi", "Nữ", "20/11/2022", "079322022073", "7940073949", "131/13 Tôn Đản P. Khánh Hội", "Lê Phạm Phương Thúy", "079192020002", "0925628561", "Mầm"),
    (93, "Châu Tuệ Nghi", "Nữ", "28/02/2022", "079322010844", "7939893994", "39-39B Cao ốc The Tresor TS1 14.15 Bến Vân Đồn", "Nguyễn Thị Nhung", "040193037150", "0988937766", "Mầm"),
    (94, "Nguyễn Thành An", "Nam", "23/03/2022", "079222006604", "7939872820", "222/11 Đoàn Văn Bơ P.Khánh Hội", "Lê Quỳnh Yên", "058191000474", "0964209763", "Mầm"),
    (95, "Trần Tâm Huệ Vân", "Nữ", "02/02/2022", "079322002221", "7939860699", "43/20 Đoàn Như Hài P.Xóm Chiếu", "Trần Thị Dung Em", "091174000078", "0938363236", "Mầm"),
    (96, "Trần Nam Anh", "Nam", "11/08/2021", "079221037511", "7939855292", "15 Đường 48 P.Vĩnh Hội", "Nguyễn Phương Mai", "001188011841", "0971531738", "Chồi"),
    (97, "Phạm Võ Linh Đan", "Nữ", "27/12/2021", "079321033268", "TE1797939844368", "242/18 Tôn Đản P.Khánh Hội", "Võ Kim Hằng", "079195034398", "0931834448", "Chồi"),
    (98, "Trần Ngọc Hạo Đăng", "Nam", "06/9/2021", "079221022230", "TE1797939803879", "55 Nguyễn Trường Tộ P. Xóm Chiếu", "Trần Nguyễn Bảo Trân", "082178000312", "0798882001", "Chồi"),
    (99, "Đặng Nguyễn Thiên Di", "Nữ", "18/10/2021", "079321030199", "TE1797939833055", "810W1 Đoàn Văn Bơ P.Khánh Hội", "/", "079198023992", "0767516679", "Chồi"),
    (100, "Tô Hoàng Mỹ Dung", "Nữ", "28/04/2021", "079321012346", "TE1797939783380", "L33181 Hoàng Diệu P.Khánh Hội", "Đỗ Thanh Thảo", "079189035580", "0909791428", "Chồi"),
    (101, "Nguyễn Hoàng Khả Hân", "Nữ", "19/04/2021", "079321009360", "TE1797939775027", "158/10 Đoàn Văn Bơ P.Khánh Hội", "Phạm Minh Hoàng Yến", "079191017589", "0906786009", "Chồi"),
    (102, "Nguyễn Trương Minh Hiếu", "Nam", "24/05/2021", "051121003441", "TE1515121817314", "32/5 Đường 25 P.Hiệp Bình", "Trương Thị Ngọc Ánh", "051187002600", "0363117689", "Chồi"),
    (103, "Trương Khoa Hưng", "Nam", "09/05/2021", "079221016012", "TE1797939795993", "B426 Đoàn Văn Bơ P.Xóm Chiếu", "", "079195018224", "0767183132", "Chồi"),
    (104, "Lê Phúc Hưng", "Nam", "21/05/2021", "079221013758", "TE1797939784677", "83/32 Hoàng Diệu P. Xóm Chiếu", "Bành Thị Loan", "079195001341", "0383524399", "Chồi"),
    (105, "Nguyễn Đặng Minh Khoa", "Nam", "18/07/2021", "037221005786", "TE1373721389913", "267/25 Đoàn Văn Bơ P. Xóm Chiếu", "Đặng Thị Thu", "037192001618", "0345744312", "Chồi"),
    (106, "Nguyễn Ngọc Khôi", "Nam", "16/01/2021", "079221006556", "TE1797939765326", "109D/19/23A Bến Vân Đồn P.Khánh Hội", "Nguyễn Ngọc Linh", "079195032771", "0904444731", "Chồi"),
    (107, "Trần Đăng Khôi", "Nam", "08/04/2021", "079221008300", "7939770427", "254/10 Bến Vân Đồn P. Vĩnh Hội", "Nguyễn Thị Tuyết Ngân", "079191022994", "0902770218", "Chồi"),
    (108, "Lê Hoàng Kim Ngân", "Nữ", "20/08/2021", "079321015952", "TE1797939794163", "250 Tôn Đản P.Khánh Hội", "Phạm Hoàng Nhi", "079191017417", "0795559976", "Chồi"),
    (109, "Tăng Ngọc Nhi", "Nữ", "19/01/2021", "079321000890", "TE1797939750511", "83/1 Tôn Đản P.Khánh Hội", "Mai Ngọc Hiếu Thảo", "079191014609", "0933491462", "Chồi"),
    (110, "Phạm Nguyễn Yến Nhi", "Nữ", "10/12/2021", "079321036881", "7939888611", "92B/20/21 Tôn Thất Thuyết P.Xóm Chiếu", "Nguyễn Thị Thanh Hòa", "079198011773", "0794972201", "Chồi"),
    (111, "Đinh Tuệ Như", "Nữ", "21/04/2021", "079321039088", "", "37/15 Đoàn Như Hài P. Xóm Chiếu", "Vương Khải Hoàn", "079076007641", "0345673798", "Chồi"),
    (112, "Nguyễn An Phúc", "Nam", "22/9/2021", "079221021782", "TE1797939803422", "A70 KDC Nam Long Phú Thuận P. Phú Thuận", "Nguyễn Minh Thiện", "079191014643", "0934560525", "Chồi"),
    (113, "Tạ Thiên Phúc", "Nam", "14/01/2021", "079221003416", "TE1797939757526", "129/26 Lô O Bến Vân Đồn P.Khánh Hội", "Nguyễn Thị Cẩm Tiên", "091193010767", "0927233555", "Chồi"),
    (114, "Quách Gia Phúc", "Nam", "20/04/2021", "079221008546", "TE1797939770866", "500/85/5 Đoàn Văn Bơ P.Khánh Hội", "Nguyễn Thị Kim Trâm", "079190018667", "0938778711", "Chồi"),
    (115, "Từ Thiên Phúc", "Nam", "06/10/2021", "079221019222", "TE1797939797670", "198/14B Tôn Đản P.Khánh Hội", "Huỳnh Thị Kim Ngọc", "079181001497", "0909452289", "Chồi"),
    (116, "Lê Đan Thanh", "Nữ", "28/06/2021", "079321020568", "TE1797939803480", "24 Đường số 40 P.Khánh Hội", "Lê Thanh Trúc", "089193007306", "0795909900", "Chồi"),
    (117, "Trần Gia Thành", "Nam", "09/11/2021", "079221028107", "TE1797939820946", "168/10 Đoàn Văn Bơ P.Khánh Hội", "Võ Thị Mỹ Linh", "079191017418", "0936134217", "Chồi"),
    (118, "Nguyễn Phương Thịnh", "Nam", "03/08/2021", "079221025536", "TE1797939815246", "120/7 Lê Quốc Hưng P. Xóm Chiếu", "Lư Bích Phượng", "079185017292", "0903897178", "Chồi"),
    (119, "Phan Ngọc Phương Thùy", "Nữ", "20/10/2021", "079321037810", "7940057044", "83/19 Hoàng Diệu P. Xóm Chiếu", "Nguyễn Thị Kiều Duyên", "089300005586", "0587022305", "Chồi"),
    (120, "Nguyễn Hoàng Minh Trí", "Nam", "04/05/2021", "079221010662", "TE1797939776567", "207/34 Lê Quốc Hưng P. Xóm Chiếu", "Nguyễn Thị Hường", "060193000071", "0931815900", "Chồi"),
    (121, "Lê Ngọc Tường Vy", "Nữ", "06/12/2021", "079321029634", "TE1797939831130", "233/1 Hoàng Diệu P.Khánh Hội", "Hồ Ngọc Ánh Dương", "079196013208", "0901348480", "Chồi"),
    (122, "Nguyễn Trúc Mây", "Nữ", "16/08/2021", "079321018930", "TE1797939802922", "31CT Tam Đảo P. Hòa Hưng", "Tăng Thị Kim Chi", "075189000023", "0903100204", "Chồi"),
    (123, "Trương Ngọc Tâm An", "Nữ", "25/10/2021", "079321025491", "TE1797939820541", "220 C/cư Đoàn Văn Bơ P.Xóm Chiếu", "Trần Ngọc Thảo", "079187035351", "0937111087", "Chồi"),
    (124, "Nguyễn Mỹ An", "Nữ", "20/09/2021", "079321022253", "TE1797939806957", "B19.22 C/cư Rivergate Bến Vân Đồn", "Nguyễn Thị Mỹ Linh", "079195029937", "0707755577", "Chồi"),
    (125, "Lâm Khả Hân", "Nữ", "11/05/2021", "079321014701", "TE1797939786253", "204/17 Lê Quốc Hưng", "Lâm Thị Hoa", "080195000395", "0938879746", "Chồi"),
    (126, "Trần Tâm Huệ Hảo", "Nữ", "01/6/2021", "079321012777", "TE1797939784779", "43/20 Đoàn Như Hài P.Xóm Chiếu", "Trần Thị Dung Em", "091174000078", "0938363236", "Chồi"),
    (127, "Trần Tâm Huệ Trinh", "Nữ", "10/05/2021", "079321010471", "TE1797939779182", "43/20 Đoàn Như Hài P.Xóm Chiếu", "Trần Thị Dung Em", "091174000078", "0938363236", "Chồi"),
]

# Ward names as they appear in the site's "Phường/Xã sau sáp nhập" dropdown.
# The address column uses abbreviated forms (P.Khánh Hội, X.Bình Hưng, ...).
WARD_PATTERNS = [
    ("khánh hội", "Phường Khánh Hội"),
    ("xóm chiếu", "Phường Xóm Chiếu"),
    ("vĩnh hội", "Phường Vĩnh Hội"),
    ("bình đông", "Phường Bình Đông"),
    ("an lạc", "Phường An Lạc"),
    ("chợ quán", "Phường Chợ Quán"),
    ("hiệp bình", "Phường Hiệp Bình"),
    ("nhà bè", "Xã Nhà Bè"),
    ("bình hưng", "Xã Bình Hưng"),
    ("hòa hưng", "Phường Hòa Hưng"),
    ("phú thuận", "Phường Phú Thuận"),
]


def extract_ward(address: str) -> Optional[str]:
    """Resolve the child's ward from the free-text address, or None if unclear."""
    addr = address.lower()
    for needle, ward in WARD_PATTERNS:
        if needle in addr:
            return ward
    return None


def normalize_dob(dob: str) -> str:
    """The PDF writes some dates as 06/9/2021; the form wants dd/MM/yyyy."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", dob.strip())
    if not m:
        raise ValueError(f"Unparseable date: {dob!r}")
    day, month, year = m.groups()
    return f"{int(day):02d}/{int(month):02d}/{year}"


def build() -> List[Dict[str, str]]:
    records = []
    for tt, name, gender, dob, cccd, bhyt, address, mother, mother_cccd, phone, lop in ROWS:
        records.append({
            "tt": tt,
            "child_name": name,
            "gender": gender,
            "dob": normalize_dob(dob),
            "child_cccd": cccd,
            "bhyt": bhyt,
            "address": address,
            "ward": extract_ward(address),
            "mother_name": mother,
            "mother_cccd": mother_cccd,
            "phone": phone,
            "school_name": SCHOOL_NAME,
            "school_address": SCHOOL_ADDRESS,
            "school_ward": SCHOOL_WARD,
            "lop": lop,
        })
    return records


def main() -> None:
    records = build()

    out = "scripts/parsed_children_mn12.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(records)} records to {out}")

    # Surface anything that needs a human decision before the import runs.
    cccds = [r["child_cccd"] for r in records]
    dupes = {c for c in cccds if cccds.count(c) > 1}
    if dupes:
        print(f"\nDUPLICATE child CCCD in the PDF: {dupes}")

    no_ward = [r for r in records if not r["ward"]]
    if no_ward:
        print(f"\nAddress with no recognizable ward ({len(no_ward)}):")
        for r in no_ward:
            print(f"  TT {r['tt']:>3} {r['child_name']:<28} {r['address']}")

    no_bhyt = [r for r in records if not r["bhyt"]]
    print(f"\nNo BHYT number ({len(no_bhyt)}): " + ", ".join(f"TT{r['tt']} {r['child_name']}" for r in no_bhyt))

    no_mother = [r for r in records if not r["mother_name"] or r["mother_name"] == "/"]
    print(f"No mother name ({len(no_mother)}): " + ", ".join(f"TT{r['tt']} {r['child_name']}" for r in no_mother))

    bad_cccd = [r for r in records if not re.fullmatch(r"\d{12}", r["child_cccd"])]
    if bad_cccd:
        print(f"Malformed child CCCD: " + ", ".join(f"TT{r['tt']} {r['child_cccd']}" for r in bad_cccd))

    print("\nPer-class counts:")
    for lop in ["Thỏ trắng", "Sóc nâu", "Họa Mi", "Mầm", "Chồi"]:
        print(f"  {lop:<12} {sum(1 for r in records if r['lop'] == lop)}")


if __name__ == "__main__":
    main()
