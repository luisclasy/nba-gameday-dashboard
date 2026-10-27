# -*- coding: utf-8 -*-
"""
中文名映射数据（NBA 观赛辅助系统“显示中文翻译”开关使用）。

- TEAM_CN：30 支球队缩写 -> 中文名（全覆盖）
- PLAYER_CN：中文别名/昵称 -> (SQL 匹配串, 显示名)，供搜索使用
- PLAYER_NICK：去重音小写姓名子串 -> 中文昵称（仅放直译姓氏会歧义/过长的少数球星）
- SURNAME_CN：英文姓氏 -> 中文姓氏（覆盖 2026 常规赛 + 2025 季后赛全体球员）
翻译优先级：PLAYER_NICK（全名/独特姓命中） -> SURNAME_CN（中文姓氏） -> 英文姓氏兜底。
"""

TEAM_CN = {
    "ATL": "老鹰", "BOS": "凯尔特人", "BKN": "篮网", "CHA": "黄蜂", "CHI": "公牛",
    "CLE": "骑士", "DAL": "独行侠", "DEN": "掘金", "DET": "活塞", "GSW": "勇士",
    "HOU": "火箭", "IND": "步行者", "LAC": "快船", "LAL": "湖人", "MEM": "灰熊",
    "MIA": "热火", "MIL": "雄鹿", "MIN": "森林狼", "NOP": "鹈鹕", "NYK": "尼克斯",
    "OKC": "雷霆", "ORL": "魔术", "PHI": "76人", "PHX": "太阳", "POR": "开拓者",
    "SAC": "国王", "SAS": "马刺", "TOR": "猛龙", "UTA": "爵士", "WAS": "奇才",
}

# 中文别名/昵称 -> (SQL 匹配串, 显示中文名)
PLAYER_CN = [
    ("库里", "Stephen Curry", "库里"), ("库", "Stephen Curry", "库里"), ("斯蒂芬", "Stephen Curry", "库里"),
    ("詹姆斯", "LeBron James", "詹姆斯"), ("老詹", "LeBron James", "詹姆斯"), ("勒布朗", "LeBron James", "詹姆斯"),
    ("杜兰特", "Kevin Durant", "杜兰特"), ("阿杜", "Kevin Durant", "杜兰特"), ("死神", "Kevin Durant", "杜兰特"),
    ("字母哥", "Antetokounmpo", "字母哥"), ("扬尼斯", "Antetokounmpo", "字母哥"),
    ("约基奇", "Jokić", "约基奇"), ("约老师", "Jokić", "约基奇"),
    ("东契奇", "Dončić", "东契奇"), ("卢卡", "Dončić", "东契奇"), ("077", "Dončić", "东契奇"),
    ("塔图姆", "Tatum", "塔图姆"), ("獭兔", "Tatum", "塔图姆"),
    ("恩比德", "Embiid", "恩比德"), ("大帝", "Embiid", "恩比德"),
    ("哈登", "James Harden", "哈登"), ("登哥", "James Harden", "哈登"),
    ("威少", "Westbrook", "威少"), ("威斯布鲁克", "Westbrook", "威少"),
    ("欧文", "Kyrie Irving", "欧文"),
    ("利拉德", "Lillard", "利拉德"), ("表哥", "Lillard", "利拉德"),
    ("戴维斯", "Anthony Davis", "戴维斯"), ("浓眉", "Anthony Davis", "浓眉"), ("AD", "Anthony Davis", "浓眉"),
    ("布克", "Devin Booker", "布克"),
    ("伦纳德", "Kawhi Leonard", "伦纳德"), ("莱昂纳德", "Kawhi Leonard", "伦纳德"), ("小卡", "Kawhi Leonard", "小卡"),
    ("乔治", "Paul George", "乔治"), ("泡椒", "Paul George", "乔治"),
    ("巴特勒", "Jimmy Butler", "巴特勒"),
    ("米切尔", "Donovan Mitchell", "米切尔"),
    ("唐斯", "Towns", "唐斯"),
    ("福克斯", "Fox", "福克斯"),
    ("文班亚马", "Wembanyama", "文班亚马"), ("文班", "Wembanyama", "文班亚马"),
    ("莫兰特", "Ja Morant", "莫兰特"),
    ("锡安", "Zion Williamson", "锡安"), ("胖虎", "Zion Williamson", "锡安"),
    ("亚历山大", "Gilgeous", "亚历山大"), ("SGA", "Gilgeous", "亚历山大"), ("鸭梨", "Gilgeous", "亚历山大"),
    ("爱德华兹", "Anthony Edwards", "爱德华兹"), ("华子", "Anthony Edwards", "爱德华兹"),
    ("杰伦布朗", "Jaylen Brown", "杰伦·布朗"), ("布朗", "Jaylen Brown", "杰伦·布朗"),
    ("霍勒迪", "Jrue Holiday", "霍勒迪"), ("假日哥", "Jrue Holiday", "霍勒迪"),
    ("特雷杨", "Trae Young", "特雷·杨"), ("吹杨", "Trae Young", "特雷·杨"),
    ("萨博尼斯", "Sabonis", "萨博尼斯"),
    ("阿德巴约", "Adebayo", "阿德巴约"),
    ("布伦森", "Brunson", "布伦森"), ("大头", "Brunson", "布伦森"),
    ("哈利伯顿", "Haliburton", "哈利伯顿"),
    ("马克西", "Maxey", "马克西"),
    ("申京", "Sengun", "申京"),
    ("巴恩斯", "Barnes", "巴恩斯"),
    ("莫布利", "Mobley", "莫布利"),
    ("德罗赞", "DeRozan", "德罗赞"),
    ("三球", "LaMelo Ball", "三球"), ("球哥", "Lonzo Ball", "球哥"),
    ("霍姆格伦", "Holmgren", "霍姆格伦"), ("切特", "Holmgren", "霍姆格伦"),
    ("追梦", "Draymond Green", "追梦·格林"), ("格林", "Draymond Green", "追梦·格林"),
    ("库明加", "Kuminga", "库明加"),
    ("穆雷", "Murray", "穆雷"), ("默里", "Murray", "穆雷"),
    ("艾顿", "Ayton", "艾顿"),
    ("里夫斯", "Reaves", "里夫斯"),
    ("八村", "Hachimura", "八村塁"), ("八村塁", "Hachimura", "八村塁"),
    ("文森特", "Vincent", "文森特"),
    ("戈贝尔", "Gobert", "戈贝尔"),
    ("拉文", "LaVine", "拉文"),
    ("兰德尔", "Randle", "兰德尔"),
    ("西亚卡姆", "Siakam", "西亚卡姆"),
    ("康宁汉姆", "Cunningham", "康宁汉姆"), ("坎宁安", "Cunningham", "康宁汉姆"),
    ("班凯罗", "Banchero", "班凯罗"),
    ("普尔", "Poole", "普尔"),
    ("波杰姆斯基", "Podziemski", "波杰姆斯基"),
]

# 去重音小写姓名子串 -> 中文昵称（直译姓氏会歧义或过长的少数球星；按表顺序首个命中）
PLAYER_NICK = [
    ("antetokounmpo", "字母哥"),
    ("luka doncic", "东契奇"),
    ("wembanyama", "文班亚马"),
    ("shai gilgeous", "亚历山大"),
    ("lamelo ball", "三球"),
    ("lonzo ball", "球哥"),
    ("anthony davis", "浓眉"),
    ("draymond green", "追梦"),
    ("zion williamson", "锡安"),
    ("trae young", "特雷·杨"),
]

# 英文姓氏 -> 中文姓氏（覆盖 2026 常规赛 + 2025 季后赛出场球员）
SURNAME_CN = {
    "Achiuwa": "阿丘瓦", "Adams": "亚当斯", "Adebayo": "阿德巴约", "Agbaji": "阿巴吉",
    "Aldama": "阿尔达马", "Alexander": "亚历山大", "Alexander-Walker": "亚历山大-沃克",
    "Allen": "艾伦", "Alvarado": "阿尔瓦拉多", "Anderson": "安德森", "Antetokounmpo": "阿德托昆博",
    "Anthony": "安东尼", "Anunoby": "阿努诺比", "Avdija": "阿夫迪亚", "Ayton": "艾顿",
    "Bagley": "巴格利", "Bailey": "贝利", "Bal": "巴尔", "Ball": "鲍尔", "Bamba": "班巴",
    "Banchero": "班凯罗", "Bane": "贝恩", "Banton": "班顿", "Barlow": "巴洛", "Barnes": "巴恩斯",
    "Barnhizer": "班海泽", "Barrett": "巴雷特", "Bassey": "巴锡", "Battle": "巴特尔",
    "Batum": "巴图姆", "Beal": "比尔", "Beasley": "比斯利", "Beauchamp": "博尚",
    "Beringer": "贝林格", "Bey": "贝", "Bitadze": "比塔泽", "Biyombo": "比永博",
    "Black": "布莱克", "Boeheim": "博海姆", "Bogdanovic": "博格达诺维奇", "Bona": "博纳",
    "Booker": "布克", "Boucher": "布歇", "Bouyea": "布耶", "Bradley": "布拉德利",
    "Branham": "布兰纳姆", "Braun": "布劳恩", "Brea": "布雷亚", "Bridges": "布里奇斯",
    "Brooks": "布鲁克斯", "Broome": "布鲁姆", "Brown": "布朗", "Brunson": "布伦森",
    "Bryant": "布莱恩特", "Bufkin": "布夫金", "Burks": "伯克斯", "Burton": "伯顿",
    "Butler": "巴特勒", "Buzelis": "布泽利斯", "Cain": "凯恩", "Caldwell-Pope": "考德威尔-波普",
    "Camara": "卡马拉", "Cancar": "钱查尔", "Capela": "卡佩拉", "Cardwell": "卡德韦尔",
    "Carlson": "卡尔森", "Carrington": "卡林顿", "Carter": "卡特", "Caruso": "卡鲁索",
    "Castle": "卡斯尔", "Castleton": "卡斯尔顿", "Champagnie": "尚帕尼", "Chandler": "钱德勒",
    "Christie": "克里斯蒂", "Cisse": "西塞", "Cissoko": "西索科", "Clark": "克拉克",
    "Clarke": "克拉克", "Clarkson": "克拉克森", "Claxton": "克拉克斯顿", "Clayton": "克莱顿",
    "Clifford": "克利福德", "Clingan": "克林根", "Clowney": "克劳尼", "Coffey": "科菲",
    "Collier": "科利尔", "Collins": "柯林斯", "Conley": "康利", "Connaughton": "康诺顿",
    "Cooke": "库克", "Cooper": "库珀", "Coulibaly": "库利巴利", "Coward": "考沃德",
    "Craig": "克雷格", "Crawford": "克劳福德", "Cryer": "克莱尔", "Cunningham": "康宁汉姆",
    "Curry": "库里", "Dadiet": "达迪耶", "Daniels": "丹尼尔斯", "Dante": "丹特",
    "Davis": "戴维斯", "Davison": "戴维森", "DeRozan": "德罗赞", "Dennis": "丹尼斯",
    "DiVincenzo": "迪温琴佐", "Diabate": "迪亚巴特", "Diawara": "迪亚瓦拉", "Dick": "迪克",
    "Dickinson": "迪金森", "Dieng": "迪昂", "Dillingham": "迪林厄姆", "Demin": "杰明",
    "Dеmin": "杰明", "Doncic": "东契奇", "Dort": "多尔特", "Dosunmu": "多苏穆",
    "Drummond": "德拉蒙德", "Dunn": "邓恩", "Durant": "杜兰特", "Duren": "杜伦",
    "Eason": "伊森", "Edey": "伊迪", "Edgecombe": "埃奇库姆", "Edwards": "爱德华兹",
    "Ellis": "埃利斯", "Embiid": "恩比德", "Enaruna": "埃纳鲁纳", "Essengue": "埃森格",
    "Etienne": "艾蒂安", "Eubanks": "尤班克斯", "Evbuomwan": "埃布奥莫万", "Fears": "菲尔斯",
    "Filipowski": "菲利波夫斯基", "Finney-Smith": "芬尼-史密斯", "Flagg": "弗拉格",
    "Fleming": "弗莱明", "Flowers": "弗劳尔斯", "Fontecchio": "丰泰基奥", "Fox": "福克斯",
    "Freeman": "弗里曼", "Fultz": "富尔茨", "Furphy": "弗菲", "Gafford": "加福德",
    "Garcia": "加西亚", "Gardner": "加德纳", "Garland": "加兰", "Garza": "加尔扎",
    "George": "乔治", "Gibson": "吉布森", "Giddey": "吉迪", "Gilbert": "吉尔伯特",
    "Gilgeous-Alexander": "吉尔杰斯-亚历山大", "Gill": "吉尔", "Gillespie": "吉莱斯皮",
    "Gobert": "戈贝尔", "Goldin": "戈尔丁", "Gonzalez": "冈萨雷斯", "Goodwin": "古德温",
    "Gordon": "戈登", "Grant": "格兰特", "Gray": "格雷", "Green": "格林", "Grimes": "格兰姆斯",
    "Gueye": "盖伊", "Hachimura": "八村塁", "Haliburton": "哈利伯顿", "Hall": "霍尔",
    "Hansen": "汉森", "Harden": "哈登", "Hardy": "哈迪", "Harkless": "哈克莱斯",
    "Harper": "哈珀", "Harris": "哈里斯", "Hart": "哈特", "Hartenstein": "哈尔滕施泰因",
    "Hauser": "豪泽", "Hawkins": "霍金斯", "Hayes": "海斯", "Hayes-Davis": "海斯-戴维斯",
    "Henderson": "亨德森", "Hendricks": "亨德里克斯", "Hepburn": "赫本", "Herro": "希罗",
    "Hield": "希尔德", "Highsmith": "海史密斯", "Hinson": "欣森", "Holiday": "霍勒迪",
    "Holland": "霍兰德", "Holmes": "霍姆斯", "Holmgren": "霍姆格伦", "Horford": "霍福德",
    "Houstan": "休斯坦", "Howard": "霍华德", "Huerter": "许尔特", "Huff": "赫夫",
    "Hukporti": "胡克波尔蒂", "Hunter": "亨特", "Huntley": "亨特利", "Hyland": "海兰德",
    "Ighodaro": "伊戈达罗", "Ingles": "英格尔斯", "Ingram": "英格拉姆", "Isaac": "艾萨克",
    "Ivey": "艾维", "Jackson": "杰克逊", "Jackson-Davis": "杰克逊-戴维斯",
    "Jakucionis": "雅库乔尼斯", "James": "詹姆斯", "Jarreau": "贾罗", "Jeffries": "杰弗里斯",
    "Jemison": "杰米森", "Jenkins": "詹金斯", "Jerome": "杰罗姆", "Joe": "乔",
    "Johnson": "约翰逊", "Jokic": "约基奇", "Jones": "琼斯", "Jordan": "乔丹",
    "Joseph": "约瑟夫", "Jovic": "约维奇", "Juzang": "朱赞", "Kalkbrenner": "卡尔克布伦纳",
    "Kawamura": "河村", "Keels": "基尔斯", "Kelly": "凯利", "Kennard": "肯纳德",
    "Kent": "肯特", "Kessler": "凯斯勒", "Key": "基", "Kispert": "基斯珀特",
    "Kleber": "克勒贝尔", "Klintman": "克林特曼", "Knecht": "克内克特", "Knox": "诺克斯",
    "Knueppel": "克努佩尔", "Kolek": "科莱克", "Koloko": "科洛科", "Konchar": "孔查尔",
    "Kornet": "科内特", "Krejci": "克雷伊奇", "Kuminga": "库明加", "Kuzma": "库兹马",
    "LaRavia": "拉拉维亚", "LaVine": "拉文", "Labissiere": "拉比西埃", "Landale": "兰代尔",
    "Lanier": "拉尼尔", "Larsson": "拉尔松", "Lawson": "劳森", "LeVert": "勒韦尔",
    "Len": "莱恩", "Leonard": "伦纳德", "Leons": "莱昂斯", "Liddell": "利德尔",
    "Lillard": "利拉德", "Lively": "莱夫利", "Livers": "利弗斯", "Livingston": "利文斯顿",
    "Looney": "卢尼", "Lopez": "洛佩斯", "Love": "勒夫", "Lovering": "洛夫林",
    "Lowry": "洛瑞", "Maluach": "马卢阿赫", "Mamukelashvili": "马穆克拉什维利", "Mann": "曼",
    "Manon": "马尼翁", "Markkanen": "马尔卡宁", "Marshall": "马歇尔", "Martin": "马丁",
    "Mashack": "马沙克", "Mathews": "马修斯", "Mathurin": "马瑟林", "Matkovic": "马特科维奇",
    "Maxey": "马克西", "Mbeng": "姆本", "McBride": "麦克布莱德", "McCain": "麦凯恩",
    "McClung": "麦克朗", "McCollum": "麦科勒姆", "McConnell": "麦康奈尔",
    "McDaniels": "麦克丹尼尔斯", "McDermott": "麦克德莫特", "McGowens": "麦戈文斯",
    "McLaughlin": "麦克劳克林", "McNeeley": "麦克尼利", "Melton": "梅尔顿", "Merrill": "梅里尔",
    "Middleton": "米德尔顿", "Miller": "米勒", "Mills": "米尔斯", "Milton": "米尔顿",
    "Minix": "米尼克斯", "Minott": "米诺特", "Missi": "米西", "Mitchell": "米切尔",
    "Mobley": "莫布利", "Mogbo": "莫格博", "Monk": "蒙克", "Moody": "穆迪",
    "Morales": "莫拉莱斯", "Morant": "莫兰特", "Morris": "莫里斯", "Murphy": "墨菲",
    "Murray": "穆雷", "Murray-Boyles": "穆雷-博伊尔斯", "Mykhailiuk": "米哈伊柳克",
    "Nance": "南斯", "Nelson": "尼尔森", "Nembhard": "内姆布哈德", "Nesmith": "内史密斯",
    "Newell": "纽厄尔", "Newton": "牛顿", "Niederhauser": "尼德豪泽", "Nnaji": "纳吉",
    "Nurkic": "努尔基奇", "O'Neale": "奥尼尔", "Oduro": "奥杜罗", "Okani": "奥卡尼",
    "Okeke": "奥基基", "Okogie": "奥科吉", "Okongwu": "奥孔武", "Okoro": "奥科罗",
    "Olbrich": "奥尔布里希", "Olynyk": "奥利尼克", "Omier": "奥米尔", "Paul": "保罗",
    "Payne": "佩恩", "Payton": "佩顿", "Peavy": "皮维", "Pedulla": "佩杜拉", "Penda": "彭达",
    "Peter": "彼得", "Peterson": "彼得森", "Phillips": "菲利普斯", "Pickett": "皮克特",
    "Plowden": "普洛登", "Plumlee": "普拉姆利", "Podziemski": "波杰姆斯基", "Poeltl": "珀尔特尔",
    "Poole": "普尔", "Portis": "波蒂斯", "Porzingis": "波尔津吉斯", "Post": "波斯特",
    "Potter": "波特", "Poulakidas": "普拉基达斯", "Powell": "鲍威尔", "Prince": "普林斯",
    "Pritchard": "普里查德", "Proctor": "普罗克特", "Prosper": "普罗斯珀", "Pullin": "普林",
    "Queen": "奎因", "Queta": "奎塔", "Quickley": "奎克利", "Randle": "兰德尔",
    "Raynaud": "雷诺", "Reath": "里斯", "Reaves": "里夫斯", "Reed": "里德", "Reese": "里斯",
    "Reeves": "里夫斯", "Reid": "里德", "Richard": "理查德", "Richards": "理查兹",
    "Richardson": "理查德森", "Richmond": "里士满", "Riley": "莱利", "Risacher": "里萨谢",
    "Robinson": "罗宾逊", "Robinson-Earl": "罗宾逊-厄尔", "Roddy": "罗迪", "Rollins": "罗林斯",
    "Rupert": "吕佩尔", "Russell": "拉塞尔", "Ryan": "瑞安", "Sabonis": "萨博尼斯",
    "Salaun": "萨兰", "Sallis": "萨利斯", "Sanders": "桑德斯", "Sandfort": "桑德福特",
    "Santos": "桑托斯", "Saraf": "萨拉夫", "Saric": "萨里奇", "Sarr": "萨尔",
    "Sasser": "萨瑟", "Scheierman": "沙伊尔曼", "Schroder": "施罗德", "Scott": "斯科特",
    "Sears": "西尔斯", "Sengun": "申京", "Sensabaugh": "森萨博", "Sexton": "塞克斯顿",
    "Shamet": "沙梅特", "Sharpe": "夏普", "Shead": "希德", "Sheppard": "谢泼德",
    "Shulga": "舒尔加", "Siakam": "西亚卡姆", "Silva": "席尔瓦", "Simmons": "西蒙斯",
    "Simons": "西蒙斯", "Simpson": "辛普森", "Sims": "西姆斯", "Slawson": "斯劳森",
    "Small": "斯莫尔", "Smart": "斯马特", "Smith": "史密斯", "Sochan": "索汉",
    "Spencer": "斯宾塞", "Stevens": "史蒂文斯", "Stewart": "斯图尔特", "Strawther": "斯特劳瑟",
    "Strus": "斯特鲁斯", "Suggs": "萨格斯", "Tate": "泰特", "Tatum": "塔图姆",
    "Telfort": "特尔福特", "Temple": "坦普尔", "Terry": "特里", "Thiero": "谢罗",
    "Thomas": "托马斯", "Thompson": "汤普森", "Thybulle": "赛布尔", "Tillman": "蒂尔曼",
    "Timme": "蒂米", "Tomlin": "汤姆林", "Tonje": "通杰", "Topic": "托皮奇", "Toppin": "托平",
    "Towns": "唐斯", "Traore": "特拉奥雷", "Travers": "特拉弗斯", "Tshiebwe": "希布维",
    "Tucker": "塔克", "Turner": "特纳", "Tyson": "泰森", "Umude": "乌穆德",
    "Valanciunas": "瓦兰丘纳斯", "VanVleet": "范弗利特", "Vanderbilt": "范德比尔特",
    "Vassell": "瓦塞尔", "Vincent": "文森特", "Vucevic": "武切维奇", "Vukcevic": "武克切维奇",
    "Wade": "韦德", "Wagner": "瓦格纳", "Walker": "沃克", "Wallace": "华莱士",
    "Walsh": "沃尔什", "Walter": "沃尔特", "Ware": "韦尔", "Washington": "华盛顿",
    "Waters": "沃特斯", "Watford": "沃特福德", "Watkins": "沃特金斯", "Watson": "沃森",
    "Wells": "威尔斯", "Wembanyama": "文班亚马", "Wesley": "韦斯利", "Westbrook": "威斯布鲁克",
    "White": "怀特", "Whitehead": "怀特黑德", "Whitmore": "惠特莫尔", "Wiggins": "维金斯",
    "Williams": "威廉姆斯", "Williamson": "威廉森", "Wilson": "威尔逊", "Wiseman": "怀斯曼",
    "Wolf": "沃尔夫", "Wright": "赖特", "Yabusele": "亚布塞莱", "Young": "杨",
    "Youngblood": "扬布拉德", "Yurtseven": "尤尔特塞文", "Zikarsky": "齐卡斯基", "Zubac": "祖巴茨",
}


import re
import unicodedata


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def cn_team(abbr):
    return TEAM_CN.get((abbr or "").strip(), abbr)


def cn_player(name):
    """英文名 -> 中文（昵称 > 中文姓氏 > 英文姓氏兜底）。"""
    if not name:
        return name
    nn = _norm(name)
    for m, cn in PLAYER_NICK:
        if m in nn:
            return cn
    s = re.sub(r"\s+(Jr\.?|Sr\.?|III|II|IV)\s*$", "", str(name).strip(), flags=re.I)
    parts = s.split()
    sur = parts[-1] if parts else s
    for k, v in SURNAME_CN.items():
        if _norm(k) == _norm(sur):
            return v
    return sur

