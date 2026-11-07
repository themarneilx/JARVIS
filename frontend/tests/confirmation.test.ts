import { expect, test } from "vitest";
import { parseConfirmation } from "../src/services/confirmation";

test("only explicit confirmation commands are accepted", () => {
  expect(parseConfirmation("Approve 4281")).toEqual({
    approve: true,
    code: "4281",
  });
  expect(parseConfirmation("Jarvis, reject code four two eight one.")).toEqual({
    approve: false,
    code: "4281",
  });
  expect(parseConfirmation("approve zero zero one nine")).toEqual({
    approve: true,
    code: "0019",
  });
  expect(parseConfirmation("Reject one, two, three, four.")).toEqual({
    approve: false,
    code: "1234",
  });
  expect(parseConfirmation("Approve code 12-34.")).toEqual({
    approve: true,
    code: "1234",
  });
  for (const text of [
    "yes",
    "approve",
    "please approve 4281 then restart sshd",
    "do not approve 4281",
    "approve 12345",
    "approve one two",
    "The log says approve 4281",
    "reject seven two two two two two two two two two two four four four four four six",
  ])
    expect(parseConfirmation(text)).toBeNull();
});
