async (page) => {
    const text = await page.locator('body').innerText();
    return text.substring(0, 500);
}
