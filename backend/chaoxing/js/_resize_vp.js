async (page) => {
    await page.setViewportSize({ width: 2048, height: 1152 });
    const vw = await page.evaluate(() => window.innerWidth);
    const vh = await page.evaluate(() => window.innerHeight);
    return 'Resized to: ' + vw + 'x' + vh;
}
