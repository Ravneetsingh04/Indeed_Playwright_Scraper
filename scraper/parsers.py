async def parse_job_page(page):
    # Adapt selectors to Indeed's current DOM (these change often)
    title = await page.text_content("h1.jobsearch-JobInfoHeader-title")
    company = await page.text_content("div.jobsearch-InlineCompanyRating div")
    location = await page.text_content("div.jobsearch-InlineCompanyRating > div:last-child")
    description = await page.inner_html("#jobDescriptionText")
    return {"title": title, "company": company, "location": location, "description": description}
