// script.js

// ฟังก์ชันทักทายเมื่อโหลดเว็บ
document.addEventListener("DOMContentLoaded", function () {
  console.log("Script.js ทำงานแล้ว ✅");

  // ตัวอย่าง: ให้ทุก row ของตาราง highlight เมื่อคลิก
  const rows = document.querySelectorAll("table tbody tr");
  rows.forEach(row => {
    row.addEventListener("click", () => {
      rows.forEach(r => r.classList.remove("selected")); // ลบสีเก่า
      row.classList.add("selected"); // เพิ่มสีใหม่
    });
  });
});
