from auth import TenderTigerAuth
from search import TenderTigerSearch
from config import EMAIL, PASSWORD
import json
from parser import TenderParser
from detail import TenderTigerDetail
from documents import TenderTigerDocuments

parsed = []
auth = TenderTigerAuth()
print(f"---------Opening login page...{auth}")
auth.open_login_page()
print(f"----------Logging in...{auth}")
auth.login(EMAIL, PASSWORD) 
print(f"-----------Logged in as: {auth.user['Email']}  ---{auth}")
search = TenderTigerSearch(auth)

result = search.search("solar")
result = json.loads(result)
# Save to file
data = json.dumps(result, indent=4)
with open("search_result.json", "w", encoding="utf-8") as f:
    f.write(data)

print("Saved to search_result.json")
# print(data)

for tender in result["TenderList"]:
    parsed.append(TenderParser.parse(tender))

# print(parsed[0])


# detail = TenderTigerDetail(auth)
# html = detail.get_detail_page(
#     parsed[0]["description_url"]
# )
# with open("detail.html", "w", encoding="utf-8") as f:
#     f.write(html)

docs = TenderTigerDocuments(auth)

html = docs.get_documents(
    tc_no="99067069",
    tender_proc_id="101461730",
    closing_date="14-Aug-2026",
)

documents = docs.parse_documents(html)

print(documents)

with open("docs.html","w",encoding="utf8") as f:
    f.write(html)