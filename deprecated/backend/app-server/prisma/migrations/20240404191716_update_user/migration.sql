/*
  Warnings:

  - You are about to drop the column `phoneId` on the `User` table. All the data in the column will be lost.
  - You are about to drop the column `usernameId` on the `User` table. All the data in the column will be lost.
  - You are about to drop the `UserPhone` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `UserShrotname` table. If the table is not empty, all the data it contains will be lost.
  - A unique constraint covering the columns `[phone]` on the table `User` will be added. If there are existing duplicate values, this will fail.
  - A unique constraint covering the columns `[username]` on the table `User` will be added. If there are existing duplicate values, this will fail.
  - Added the required column `phone` to the `User` table without a default value. This is not possible if the table is not empty.
  - Added the required column `username` to the `User` table without a default value. This is not possible if the table is not empty.

*/
-- DropForeignKey
ALTER TABLE "User" DROP CONSTRAINT "User_phoneId_fkey";

-- DropForeignKey
ALTER TABLE "User" DROP CONSTRAINT "User_usernameId_fkey";

-- AlterTable
ALTER TABLE "User" DROP COLUMN "phoneId",
DROP COLUMN "usernameId",
ADD COLUMN     "phone" TEXT NOT NULL,
ADD COLUMN     "username" TEXT NOT NULL;

-- DropTable
DROP TABLE "UserPhone";

-- DropTable
DROP TABLE "UserShrotname";

-- CreateIndex
CREATE UNIQUE INDEX "User_phone_key" ON "User"("phone");

-- CreateIndex
CREATE UNIQUE INDEX "User_username_key" ON "User"("username");
