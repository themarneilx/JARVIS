export async function holdMicrophone(page, locator, milliseconds, whileHeld) {
  await locator.scrollIntoViewIfNeeded();
  const box=await locator.boundingBox();
  if(!box)throw new Error('Microphone button is not visible');
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
  await page.mouse.down();
  try {
    if(whileHeld)await whileHeld();
    await page.waitForTimeout(milliseconds);
  } finally {
    await page.mouse.up();
  }
}
